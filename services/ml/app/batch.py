"""Batch / scheduled job entry points for the ML service.

Run as a module, e.g.:
    python -m app.batch health
    python -m app.batch refresh-matviews
    python -m app.batch register-model --name drishti-risk --type classification --version 1.0.0
    python -m app.batch demo-score --district 1 --score 0.8

These are the CLI hooks a scheduler (cron / Airflow-style) invokes for nightly
re-scoring and matview refresh (doc 02 §9). Model scoring itself lands in
Phases 6-13; this provides the runnable skeleton + the refresh step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

from . import db, matviews, models
from .config import get_settings


def _cmd_health(_args) -> int:
    try:
        ok = db.ping()
        exts = db.installed_extensions()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "degraded", "error": str(exc).strip()}))
        return 1
    required = {e: (e in exts) for e in ("postgis", "vector", "pg_trgm")}
    status = "ok" if ok and all(required.values()) else "degraded"
    print(json.dumps({"status": status, "database": ok,
                      "extensions": {**required, "pgrouting": "pgrouting" in exts}}))
    return 0 if status == "ok" else 1


def _cmd_refresh_matviews(args) -> int:
    names = args.views or list(matviews.ALL_MATVIEWS)
    with db.rw_conn() as conn:
        result = matviews.refresh_all(conn, names)
    print(json.dumps({"refreshed": result}))
    return 0


def _cmd_register_model(args) -> int:
    with db.rw_conn() as conn:
        mv_id = models.get_or_create_model_version(
            conn, model_name=args.name, model_type=args.type, version=args.version,
            framework=args.framework,
        )
        label = models.model_version_label(conn, mv_id)
    print(json.dumps({"model_version_id": mv_id, "model_version": label}))
    return 0


def _cmd_enrich_graph(args) -> int:
    from .graph import enrich
    print(json.dumps(enrich.run(seed=args.seed), default=str))
    return 0


def _cmd_communities(args) -> int:
    from .graph import algorithms
    with db.rw_conn() as conn:
        result = algorithms.detect_communities(conn)
    print(json.dumps(result, default=str))
    return 0


def _cmd_centrality(args) -> int:
    from .graph import algorithms
    with db.rw_conn() as conn:
        result = algorithms.compute_centrality(conn, betweenness_k=args.betweenness_k)
    print(json.dumps(result, default=str))
    return 0


def _cmd_hidden_associations(args) -> int:
    from .graph import hidden
    with db.rw_conn() as conn:
        result = hidden.materialize(conn, min_links=args.min_links)
    print(json.dumps(result, default=str))
    return 0


def _cmd_load_curated_case(args) -> int:
    """Load the curated public-source case record through the real FIR path.

    Writes no biometric material for any real person: see the module docstring in
    app/cases/curated_public_case.py. Loading this case moves the analytics-policy
    digest, so the reminder below is printed rather than left to be rediscovered
    when /geo/hotspots starts failing closed.
    """
    from .cases import curated_public_case as curated
    with db.rw_conn() as conn:
        result = curated.load(conn, actor=args.actor)
    print(json.dumps(result, indent=2, default=str))
    if result.get("status") == "loaded":
        print("\nNOTE: curated case material changes the analytics-policy digest. "
              "Re-run: hotspots, emerging-alerts, workload-run", flush=True)
    return 0 if result.get("status") == "loaded" else 1


def _cmd_hotspots(args) -> int:
    from .geo import hotspots
    with db.rw_conn() as conn:
        result = hotspots.run_hotspots(conn, eps_m=args.eps_m, eps_days=args.eps_days,
                                       min_samples=args.min_samples)
    print(json.dumps(result, default=str))
    return 0


def _cmd_emerging_alerts(args) -> int:
    from .geo import alerts
    with db.rw_conn() as conn:
        result = alerts.detect_and_write(conn, window=args.window,
                                         threshold_sigma=args.threshold_sigma)
    print(json.dumps(result, default=str))
    return 0


def _cmd_risk_score(args) -> int:
    from .risk import scoring
    with db.rw_conn() as conn:
        result = scoring.score_all(conn, context_size=args.context_size,
                                   limit=args.limit, foundation_estimators=args.estimators)
    print(json.dumps(result, default=str))
    return 0


def _cmd_risk_calibration(args) -> int:
    from .risk import scoring
    with db.rw_conn() as conn:
        result = scoring.calibration_report(conn)
    print(json.dumps(result, default=str))
    return 0


def _cmd_embed_cases(args) -> int:
    from .cases import corpus
    with db.rw_conn() as conn:
        result = corpus.embed_corpus(conn, limit=args.limit, batch_size=args.batch_size,
                                     embedder_name=args.embedder)
    print(json.dumps(result, default=str))
    return 0


def _cmd_case_summary(args) -> int:
    from .cases import service
    resp = service.case_summary(args.case)
    if resp is None:
        print(json.dumps({"error": f"case {args.case} not found"}))
        return 1
    print(json.dumps({"summary_id": resp.summary_id, "fully_cited": resp.fully_cited,
                      "claims": resp.claim_count, "confidence": resp.confidence,
                      "model_version": resp.result.model_version}, default=str))
    return 0


def _cmd_case_leads(args) -> int:
    from .cases import service
    resp = service.case_leads(args.case)
    if resp is None:
        print(json.dumps({"error": f"case {args.case} not found"}))
        return 1
    print(json.dumps({"case": resp.case_id, "io_employee_id": resp.io_employee_id,
                      "leads": [{"rank": l.rank, "kind": l.kind, "score": l.score,
                                 "recommendation_id": l.recommendation_id} for l in resp.leads]},
                     default=str))
    return 0


def _cmd_money_detect(args) -> int:
    from .money import detection
    with db.rw_conn() as conn:
        result = detection.run_detection(
            conn, structuring_min_count=args.structuring_min_count,
            structuring_window_days=args.structuring_window_days,
            cycle_min_amount=args.cycle_min_amount, cycle_max_len=args.cycle_max_len)
    print(json.dumps(result, default=str))
    return 0


def _cmd_forecast_run(args) -> int:
    from .forecast import service
    resp = service.run_forecast(head_id=args.head_id, horizon_days=args.horizon_days)
    print(json.dumps({"head_id": resp.head_id, "horizon_days": resp.horizon_days,
                      "prediction_start": resp.prediction_start,
                      "layers": [{"layer": l.layer, "model": l.model, "written": l.written}
                                 for l in resp.layers],
                      "alerts_written": resp.alerts_written,
                      "high_severe": sum(1 for d in resp.fused if d.risk_class in ("High", "Severe")),
                      "answer": resp.result.answer}, default=str))
    return 0


def _cmd_forecast_validate(args) -> int:
    import datetime as dt
    from .forecast import service
    cut = dt.date.fromisoformat(args.cutoff) if args.cutoff else None
    resp = service.validation(cutoff=cut, horizon_months=args.horizon_months,
                              area_fraction=args.area_fraction)
    print(json.dumps({"cutoff": resp.cutoff, "overall": resp.overall,
                      "per_crime_head": resp.per_crime_head}, default=str))
    return 0


def _cmd_forecast_backtest(args) -> int:
    from .forecast import service
    resp = service.backtest(head_id=args.head_id, horizon=args.horizon,
                            n_origins=args.n_origins, per_head=not args.no_per_head,
                            persist=not args.no_persist)
    print(json.dumps({"model": resp.model, "beats_all_baselines": resp.beats_all_baselines,
                      "baselines": resp.baselines, "skill_vs_baselines": resp.skill_vs_baselines,
                      "scored_points": resp.scored_points, "abstained_cells": resp.abstained_cells,
                      "abstention_rate": resp.abstention_rate, "geo_holdout": resp.geo_holdout,
                      "error_by_season": resp.error_by_season, "error_by_head": resp.error_by_head,
                      "persisted_backtest_id": resp.persisted_backtest_id,
                      "answer": resp.result.answer}, default=str))
    return 0


def _cmd_workload_eval(args) -> int:
    from .workload import evaluation
    with db.ro_conn() as conn:
        report = evaluation.evaluate(conn, foundation_kind=args.foundation)
    print(json.dumps({
        "summary": evaluation.summarize(report),
        "beats_all_baselines": report["beats_all_baselines"],
        "model_qwk": report["model"]["calibrated"]["qwk"],
        "baselines": {k: {"qwk": v["qwk"], "accuracy": v["accuracy"]}
                      for k, v in report["baselines"].items()},
        "skill_vs_baselines": report["skill_vs_baselines"],
        "geo_holdout": report["geo_holdout"].get("metrics"),
        "abstention_rate": report["abstention"]["abstention_rate"],
        "splits": report["splits"], "leakage": report["leakage"],
        "band_thresholds": report["band_thresholds"]}, default=str))
    return 0


def _cmd_workload_run(args) -> int:
    from .workload import service
    result = service.run_governed(foundation_kind=args.foundation, limit=args.limit,
                                  lifecycle=args.lifecycle, actor="batch")
    print(json.dumps(result, default=str))
    return 0


def _cmd_workload_benchmark(args) -> int:
    from .workload import service
    result = service.run_benchmark_and_persist(include_heavy=args.heavy, actor="batch")
    cols = ("model_name", "family", "scale_label", "row_scale", "device", "total_seconds",
            "latency_ms_per_row", "throughput_rows_per_sec", "peak_rss_mb", "gpu_mem_mb",
            "accuracy", "qwk", "ece", "available", "note")
    print(json.dumps({"device": result["device"], "test_rows": result["test_rows"],
                      "train_rows_full": result["train_rows_full"],
                      "rows": [{k: r.get(k) for k in cols} for r in result["rows"]]}, default=str))
    return 0


def _cmd_geo_validate(args) -> int:
    import datetime as dt
    from .geo import validation
    with db.ro_conn() as conn:
        patterns = validation.known_patterns(conn)
    with db.rw_conn() as conn:  # PAI runs clustering; rw conn (no writes though)
        pai = validation.pai_report(conn, cutoff=dt.date.fromisoformat(args.cutoff))
    print(json.dumps({"known_patterns": patterns, "pai": pai}, default=str))
    return 0


def _cmd_face_models(args) -> int:
    """Fetch the ONNX face-recognition weights (explicit, one-time, ~275 MB).

    Deliberately NOT done lazily on the request path: a first API call must not
    block on a large download, and unannounced network egress from a request
    handler is not something an operator should have to discover.
    """
    from .face import encoders as face_encoders, modelfiles
    try:
        bundle = modelfiles.fetch(args.pack, force=args.force, log=print)
    except modelfiles.FaceModelsMissing as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1
    face_encoders.reset_encoder_cache()          # pick the real encoder up now
    print(json.dumps({"status": "ok", **bundle.describe(),
                      "encoder": face_encoders.get_encoder().describe()}, default=str))
    return 0


def _cmd_face_status(_args) -> int:
    """Report engine, model presence, gallery size and probe counts."""
    from .face import service as face_service
    print(json.dumps(face_service.status().model_dump(), default=str))
    return 0


def _cmd_face_enrol(args) -> int:
    """Enrol reference photos from a local folder into the person gallery.

    Each file is matched to a canonical person by its filename stem, which must be
    either a CanonicalPersonID (``1234.jpg``) or a PublicRef (``SYN-PERSON-000123.jpg``).
    Ambiguous or unknown stems are reported and skipped rather than guessed at —
    attaching biometrics to the wrong identity is not a recoverable mistake.
    """
    import base64
    import pathlib

    from . import db as _db
    from .face import schemas as face_schemas, service as face_service, store

    folder = pathlib.Path(args.dir).expanduser()
    if not folder.is_dir():
        print(json.dumps({"status": "failed", "error": f"{folder} is not a directory"}))
        return 1
    files = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"))
    if not files:
        print(json.dumps({"status": "failed", "error": f"no images found in {folder}"}))
        return 1

    results = {"enrolled": 0, "reused": 0, "skipped": [], "failed": []}
    for path in files:
        stem = path.stem.strip()
        cpid = None
        try:
            cpid = int(stem)
        except ValueError:
            with _db.ro_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT "CanonicalPersonID" FROM "CanonicalPerson" '
                                'WHERE "PublicRef"=%s', (stem,))
                    row = cur.fetchone()
            if row:
                cpid = int(row[0])
        if cpid is None:
            results["skipped"].append(
                {"file": path.name,
                 "reason": "filename is neither a CanonicalPersonID nor a PublicRef"})
            continue
        try:
            resp = face_service.enrol(
                face_schemas.FaceEnrolRequest(
                    image_base64=base64.b64encode(path.read_bytes()).decode("ascii"),
                    canonical_person_id=cpid, image_label=path.name,
                    make_primary=args.primary, actor="batch"),
                actor="batch")
        except Exception as exc:  # noqa: BLE001 — report and continue the batch
            results["failed"].append({"file": path.name,
                                      "error": f"{type(exc).__name__}: {exc}"})
            continue
        results["enrolled" if resp.created else "reused"] += 1
        print(f"  {path.name} -> person {cpid} "
              f"(quality {resp.quality}, gallery {resp.gallery_face_count})")

    try:
        prefer = face_service._encoder().name
    except Exception:  # noqa: BLE001 — a summary line must not fail the command
        prefer = None
    with _db.ro_conn() as conn:
        live = store.gallery_model(conn, prefer_model_name=prefer)
    results["gallery"] = ({"model_version_id": live[0], "model_name": live[1],
                           "face_count": live[2], "person_count": live[3]}
                          if live else None)
    print(json.dumps({"status": "ok", **results}, default=str))
    return 0 if not results["failed"] else 1


def _cmd_face_enrol_portraits(args) -> int:
    """Bulk-enrol a synthetic portrait dataset laid out one directory per person.

    Expects the DRISHTI_Synthetic_Portraits shape, where the PublicRef lives in
    the DIRECTORY name rather than the filename (which is why ``face-enrol``
    cannot read it)::

        <root>/portraits/SYN-PERSON-0000002_Ganesh_Pujar/
            identity.json
            synthetic_portrait.jpg

    ``identity.json`` is treated as the authoritative per-person record. The
    dataset's ``portrait_manifest.csv`` is NOT read: it has been observed to
    disagree with the files on disk (naming a ``.png`` that does not exist and
    reporting ``pending_generation`` for a portrait that is present), and
    resolving a biometric identity from a stale index is not acceptable. Even
    ``identity.json``'s own ``relative_image_path`` is verified against the
    filesystem and re-globbed when it does not resolve.

    Enrolment applies the SAME detection and quality gates as ``POST /face/enrol``
    so a fixture gallery cannot be held to a lower bar than an officer upload —
    a weak reference photo produces false matches for everyone, not just its own
    subject. Rows are written with ``EnrolmentSource='fixture_import'`` so bulk
    demo portraits stay distinguishable from evidence and officer uploads for the
    life of the gallery.

    Idempotent and resumable: the unique index on (person, image hash, model)
    means a re-run re-enrols nothing, and already-enrolled pairs are skipped
    before decode so a resumed run costs no inference.
    """
    import pathlib
    import time

    from . import audit, db as _db
    from .face import encoders as face_encoders, store

    if args.shards < 1 or not (0 <= args.shard < args.shards):
        print(json.dumps({"status": "failed",
                          "error": f"invalid shard {args.shard} of {args.shards}; "
                                   "expected --shards >= 1 and 0 <= --shard < --shards"}))
        return 1

    root = pathlib.Path(args.dir).expanduser()
    portraits = root / "portraits" if (root / "portraits").is_dir() else root
    if not portraits.is_dir():
        print(json.dumps({"status": "failed",
                          "error": f"{root} has no portraits/ directory"}))
        return 1

    # --- 1. read the dataset (identity.json per person dir) -------------------
    IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    entries: list[dict] = []          # {public_ref, path, label}
    dataset_issues: list[dict] = []
    for person_dir in sorted(p for p in portraits.iterdir() if p.is_dir()):
        ident = person_dir / "identity.json"
        public_ref, rel = None, None
        if ident.is_file():
            try:
                meta = json.loads(ident.read_text(encoding="utf-8"))
                public_ref = str(meta.get("public_ref") or "").strip() or None
                rel = str(meta.get("relative_image_path") or "").strip() or None
            except (OSError, ValueError) as exc:
                dataset_issues.append({"dir": person_dir.name,
                                       "issue": f"unreadable identity.json: {type(exc).__name__}"})
        # Directory name is the fallback key: "<PublicRef>_<Name>".
        if not public_ref:
            public_ref = person_dir.name.split("_", 1)[0]

        # Trust the filesystem over the recorded path (the dataset's own index is stale).
        image = None
        if rel:
            candidate = root / rel
            if candidate.is_file():
                image = candidate
        if image is None:
            found = sorted(p for p in person_dir.iterdir()
                           if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
            if found:
                image = found[0]
                if rel:
                    dataset_issues.append(
                        {"dir": person_dir.name, "public_ref": public_ref,
                         "issue": "identity.json relative_image_path does not exist; "
                                  f"used {image.name} found on disk instead"})
        if image is None:
            dataset_issues.append({"dir": person_dir.name, "public_ref": public_ref,
                                   "issue": "no image file in directory"})
            continue
        entries.append({"public_ref": public_ref, "path": image,
                        "label": f"{public_ref} synthetic portrait"})

    if not entries:
        print(json.dumps({"status": "failed",
                          "error": f"no portrait images found under {portraits}",
                          "dataset_issues": dataset_issues[:20]}))
        return 1
    if args.limit:
        entries = entries[: args.limit]
    total_entries = len(entries)
    # Sharding exists because ORT sessions here are lock-serialised (see
    # onnx_arcface._make_session / the per-session locks), so threads cannot
    # parallelise inference — separate processes can. Shards are disjoint and
    # deterministic, so N processes cover the dataset exactly once.
    if args.shards > 1:
        entries = [e for i, e in enumerate(entries) if i % args.shards == args.shard]
        print(f"  shard {args.shard + 1}/{args.shards}: "
              f"{len(entries)} of {total_entries} portraits")
    print(f"  dataset: {len(entries)} portraits under {portraits}")
    if dataset_issues:
        print(f"  dataset issues: {len(dataset_issues)} "
              f"(first: {dataset_issues[0]['issue']})")

    # --- 2. resolve PublicRef -> CanonicalPersonID in bulk -------------------
    refs = sorted({e["public_ref"] for e in entries})
    ref_to_cpid: dict[str, int] = {}
    merged: set[str] = set()
    with _db.ro_conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(refs), 5000):
                chunk = refs[i: i + 5000]
                cur.execute(
                    'SELECT "PublicRef","CanonicalPersonID","ResolutionStatus" '
                    'FROM "CanonicalPerson" WHERE "PublicRef" = ANY(%s)', (chunk,))
                for public_ref, cpid, status in cur.fetchall():
                    if status == "merged":
                        merged.add(public_ref)
                    else:
                        ref_to_cpid[public_ref] = int(cpid)
    print(f"  resolved {len(ref_to_cpid)}/{len(refs)} PublicRefs to canonical persons")

    # --- 3. encoder + model version ------------------------------------------
    try:
        encoder = face_encoders.get_encoder()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "failed",
                          "error": f"face encoder unavailable: {exc}"}))
        return 1
    if not encoder.biometric:
        print(json.dumps({
            "status": "failed",
            "error": "the active encoder is the non-biometric fallback; run "
                     "'python -m app.batch face-models --pack buffalo_l' first"}))
        return 1
    min_quality = (args.min_quality if args.min_quality is not None
                   else encoder.min_enrol_quality)
    with _db.rw_conn() as conn:
        model_version_id = store.model_version_for(conn, encoder)
    print(f"  encoder: {encoder.name} v{encoder.version} "
          f"(ModelVersionID {model_version_id}, min quality {min_quality:.2f})")

    # --- 4. resume: skip pairs already enrolled under this model -------------
    already: set[tuple[int, str]] = set()
    with _db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "CanonicalPersonID","ImageSha256" FROM "PersonFaceEmbedding" '
                'WHERE "ModelVersionID"=%s', (model_version_id,))
            already = {(int(r[0]), str(r[1])) for r in cur.fetchall()}
    if already:
        print(f"  gallery already holds {len(already)} descriptors for this model")

    # --- 5. encode + insert --------------------------------------------------
    counts = {"enrolled": 0, "reused": 0, "skipped_resume": 0,
              "unresolved_person": 0, "merged_person": 0,
              "no_face": 0, "low_quality": 0, "failed": 0}
    failures: list[dict] = []
    started = time.time()
    pending = 0

    # One long-lived read/write connection, committed in bounded batches. The
    # context manager keeps rw_conn()'s session setup and final commit/close
    # intact; the periodic commits inside simply bound each transaction.
    with _db.rw_conn() as conn:
        for index, entry in enumerate(entries, start=1):
            public_ref = entry["public_ref"]
            cpid = ref_to_cpid.get(public_ref)
            if cpid is None:
                counts["merged_person" if public_ref in merged
                       else "unresolved_person"] += 1
                continue
            try:
                data = entry["path"].read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                if (cpid, sha) in already:
                    counts["skipped_resume"] += 1
                    continue

                image = face_encoders.decode_image(data)
                faces = encoder.detect_and_encode(image, max_faces=1)
                if not faces:
                    counts["no_face"] += 1
                    failures.append({"public_ref": public_ref, "reason": "no face detected"})
                    continue
                face = faces[0]
                if face.quality is not None and face.quality < min_quality:
                    counts["low_quality"] += 1
                    failures.append({"public_ref": public_ref,
                                     "reason": f"quality {face.quality:.3f} < {min_quality:.2f}"})
                    continue

                _fid, created = store.enrol_face(
                    conn, canonical_person_id=cpid,
                    model_version_id=model_version_id,
                    embedding=face.embedding, image_sha256=sha,
                    bounding_box=(face.box.as_dict() if face.box else {}),
                    detector_score=face.detector_score, quality=face.quality,
                    face_count=len(faces), image_label=entry["label"],
                    enrolment_source="fixture_import", actor=args.actor,
                    make_primary=not args.no_primary)
                counts["enrolled" if created else "reused"] += 1
                already.add((cpid, sha))
                pending += 1
            except Exception as exc:  # noqa: BLE001 — report and continue the batch
                counts["failed"] += 1
                if len(failures) < 200:
                    failures.append({"public_ref": public_ref,
                                     "reason": f"{type(exc).__name__}: {exc}"})
                conn.rollback()
                pending = 0
                continue

            # Bounded transactions: a 16k-row single transaction is a long lock
            # and loses everything on one late failure.
            if pending >= args.commit_every:
                conn.commit()
                pending = 0

            if index % args.progress_every == 0 or index == len(entries):
                done = index
                rate = done / max(1e-6, time.time() - started)
                remaining = (len(entries) - done) / rate if rate else 0
                print(f"  [{done}/{len(entries)}] enrolled={counts['enrolled']} "
                      f"skipped={counts['skipped_resume']} no_face={counts['no_face']} "
                      f"low_quality={counts['low_quality']} failed={counts['failed']} "
                      f"| {rate:.1f} img/s | ETA {remaining / 60:.1f} min", flush=True)
        conn.commit()

        # One summary audit row: 16k individual rows would bury the trail that
        # matters (who searched for whom), and this is a provisioning action.
        audit.record("face.enrol.bulk", "PersonFaceEmbedding", None,
                     actor=args.actor,
                     detail={"source": "synthetic_portrait_fixture",
                             "dataset_root": str(root), "model_name": encoder.name,
                             "model_version_id": model_version_id,
                             "enrolment_source": "fixture_import",
                             "min_quality": min_quality, **counts},
                     conn=conn)

    face_count, person_count = 0, 0
    with _db.ro_conn() as ro:
        live = store.gallery_model(ro, prefer_model_name=encoder.name)
        if live:
            face_count, person_count = live[2], live[3]

    elapsed = time.time() - started
    print(json.dumps({
        "status": "ok" if not counts["failed"] else "completed_with_errors",
        "elapsed_s": round(elapsed, 1),
        "model_version_id": model_version_id, "model_name": encoder.name,
        **counts,
        "gallery": {"face_count": face_count, "person_count": person_count},
        "dataset_issues": len(dataset_issues),
        "dataset_issues_sample": dataset_issues[:5],
        "failures_sample": failures[:5],
    }, default=str))
    return 0 if not counts["failed"] else 1


def _cmd_apply_sql(args) -> int:
    import pathlib
    sql = pathlib.Path(args.file).read_text(encoding="utf-8")
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(json.dumps({"applied": args.file}))
    return 0


def _cmd_load_boundaries(_args) -> int:
    """Idempotently persist state/district/taluk jurisdiction boundaries (Phase 9)."""
    from .geo import persist
    with db.rw_conn() as conn:
        inserted = persist.ensure_boundaries(conn)
        summary = persist.summary(conn)
    print(json.dumps({"inserted": inserted, "summary": summary}))
    return 0


def _cmd_geo_scan(args) -> int:
    """Scan canonical geography for containment failures -> DataQualityIssue (Phase 9)."""
    from .geo import jurisdiction
    with db.rw_conn() as conn:
        result = jurisdiction.scan_containment(conn, scope=args.scope, actor="batch")
    print(json.dumps(result, default=str))
    return 0


def _cmd_load_derived(args) -> int:
    """Deterministic, NON-DESTRUCTIVE derived-data refresh (Prompt 18 §D.2).

    Idempotently (re)builds the derived data that the analytics / detector /
    graph routes and their tests read: materialized views, the hidden-association
    feed and money-trail flags. Optionally a bounded offender risk-score sample
    (--with-risk; heavy on CPU). It NEVER truncates or deletes base data — each
    step is an upsert / REFRESH / re-flag over the existing synthetic dataset, so
    re-running it is safe and converges to the same state. Use it to bring a fresh
    analytics DB up to a testable derived-data state without regenerating 100k FIRs.
    """
    from .graph import hidden
    from .money import detection
    steps: dict = {}
    with db.rw_conn() as conn:
        steps["matviews"] = matviews.refresh_all(conn, list(matviews.ALL_MATVIEWS))
    with db.rw_conn() as conn:
        steps["hidden_associations"] = hidden.materialize(conn, min_links=args.min_links)
    with db.rw_conn() as conn:
        steps["money_flags"] = detection.run_detection(conn)
    if args.with_risk:
        from .risk import scoring
        with db.rw_conn() as conn:
            steps["risk_scores"] = scoring.score_all(conn, limit=args.risk_limit)
    print(json.dumps({"loaded": steps,
                      "note": "non-destructive; idempotent derived-data refresh"},
                     default=str))
    return 0


# Derived/base data the analytics + detector test suites depend on: (label, SQL,
# minimum rows expected, owning test module). CrimeRiskScore is optional — the
# offender-risk read tests skip cleanly when it is empty (Phase 13 retired the
# individual score in favour of the aggregate workload band), so it is reported
# but never fails validation.
_FIXTURE_CHECKS = [
    ("SocialIndicator", 'SELECT COUNT(*) FROM "SocialIndicator"', 1, "test_analytics", True),
    ("EconomicIndicator", 'SELECT COUNT(*) FROM "EconomicIndicator"', 1, "test_analytics", True),
    ("hidden_associations", "SELECT COUNT(*) FROM drishti_hidden_associations", 1,
     "test_graph_hidden", True),
    ("money_flags", 'SELECT COUNT(*) FROM "FinancialTransaction" WHERE "IsFlagged"=true', 1,
     "test_money", True),
    ("CrimeRiskScore", 'SELECT COUNT(*) FROM "CrimeRiskScore"', 0, "test_risk (optional)", False),
]


def _cmd_validate_fixtures(_args) -> int:
    """Read-only validation that the derived-data fixtures the test suite depends
    on are present (Prompt 18 §D.2 fixture validation). Exits non-zero only when a
    REQUIRED derived table is below its minimum row count (never mutates data)."""
    results = []
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            for label, sql, minimum, owner, required in _FIXTURE_CHECKS:
                try:
                    cur.execute(sql)
                    n = int(cur.fetchone()[0])
                    ok = (n >= minimum) if required else True
                except Exception as e:  # noqa: BLE001
                    n, ok = None, (not required)
                    owner += f" [error: {str(e).splitlines()[0][:50]}]"
                results.append({"fixture": label, "rows": n, "min": minimum,
                                "required": required, "ok": ok, "owner": owner})
    failures = [r for r in results if not r["ok"]]
    print(json.dumps({"fixtures": results, "all_required_present": not failures,
                      "remediation": None if not failures
                      else "run: python -m app.batch load-derived [--with-risk]"},
                     indent=2, default=str))
    return 0 if not failures else 1


def _cmd_demo_score(args) -> int:
    with db.rw_conn() as conn:
        mv_id = models.get_or_create_model_version(
            conn, "drishti-risk-demo", "classification", "0.1.0", framework="scaffold")
        risk_id, level = models.write_crime_risk_score(
            conn, mv_id, risk_score=args.score, district_id=args.district,
            factors={"demo": True, "cli": True})
        inf_id = models.log_inference(
            conn, mv_id, inputs={"district_id": args.district, "risk_score": args.score},
            outputs={"risk_level": level, "risk_score_id": risk_id},
            confidence=args.score, ref_table="District", ref_id=str(args.district))
    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_district_risk_profile")
    print(json.dumps({"risk_score_id": risk_id, "risk_level": level,
                      "inference_id": inf_id, "model_version_id": mv_id}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="drishti-ml-batch", description=get_settings().app_name)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("health").set_defaults(func=_cmd_health)

    rm = sub.add_parser("refresh-matviews")
    rm.add_argument("--views", nargs="*", help="specific matviews (default: all)")
    rm.set_defaults(func=_cmd_refresh_matviews)

    reg = sub.add_parser("register-model")
    reg.add_argument("--name", required=True)
    reg.add_argument("--type", required=True)
    reg.add_argument("--version", required=True)
    reg.add_argument("--framework", default=None)
    reg.set_defaults(func=_cmd_register_model)

    ds = sub.add_parser("demo-score")
    ds.add_argument("--district", type=int, required=True)
    ds.add_argument("--score", type=float, default=0.5)
    ds.set_defaults(func=_cmd_demo_score)

    # ---- facial recognition ----
    fm = sub.add_parser("face-models",
                        help="download the ONNX face-recognition weights (one time, ~275 MB)")
    fm.add_argument("--pack", default="buffalo_l", choices=["buffalo_l", "buffalo_s"],
                    help="buffalo_l = ArcFace R50 (accuracy default); "
                         "buffalo_s = MobileFaceNet (~4x faster, smaller download)")
    fm.add_argument("--force", action="store_true", help="re-download even if present")
    fm.set_defaults(func=_cmd_face_models)

    fs = sub.add_parser("face-status",
                        help="report face engine, model presence, gallery size, probe counts")
    fs.set_defaults(func=_cmd_face_status)

    fe = sub.add_parser("face-enrol",
                        help="enrol reference photos from a folder (filename = "
                             "CanonicalPersonID or PublicRef)")
    fe.add_argument("--dir", required=True, help="folder of .jpg/.png reference photos")
    fe.add_argument("--primary", action="store_true",
                    help="mark each enrolled photo as that person's reference image")
    fe.set_defaults(func=_cmd_face_enrol)

    fp = sub.add_parser("face-enrol-portraits",
                        help="bulk-enrol a one-directory-per-person portrait dataset "
                             "(PublicRef taken from the directory name)")
    fp.add_argument("--dir", required=True,
                    help="dataset root (the directory containing portraits/)")
    fp.add_argument("--limit", type=int, default=0,
                    help="only process the first N portraits (0 = all)")
    fp.add_argument("--min-quality", type=float, default=None,
                    help="override the encoder's enrolment quality floor")
    fp.add_argument("--no-primary", action="store_true",
                    help="do not mark each portrait as that person's reference photo")
    fp.add_argument("--commit-every", type=int, default=200,
                    help="commit after this many enrolments")
    fp.add_argument("--progress-every", type=int, default=100,
                    help="print a progress line after this many portraits")
    fp.add_argument("--actor", default="batch.fixture_import",
                    help="actor recorded on each gallery row and the audit entry")
    fp.add_argument("--shards", type=int, default=1,
                    help="split the dataset into N disjoint shards so N processes "
                         "can run in parallel (ONNX sessions are lock-serialised, "
                         "so threads do not help)")
    fp.add_argument("--shard", type=int, default=0,
                    help="0-based index of the shard this process handles")
    fp.set_defaults(func=_cmd_face_enrol_portraits)

    ap = sub.add_parser("apply-sql", help="apply a .sql migration file")
    ap.add_argument("--file", required=True)
    ap.set_defaults(func=_cmd_apply_sql)

    lb = sub.add_parser("load-boundaries", help="persist state/district/taluk jurisdiction boundaries")
    lb.set_defaults(func=_cmd_load_boundaries)

    gs = sub.add_parser("geo-scan", help="scan canonical geography for containment failures -> DataQualityIssue")
    gs.add_argument("--scope", default="all", choices=["caseversion", "location_observation", "all"])
    gs.set_defaults(func=_cmd_geo_scan)

    ld = sub.add_parser("load-derived",
                        help="deterministic, non-destructive derived-data refresh: matviews + "
                             "hidden-associations + money flags (+ optional risk sample)")
    ld.add_argument("--min-links", type=int, default=2, help="hidden-association min shared kinds")
    ld.add_argument("--with-risk", action="store_true",
                    help="also score a bounded offender risk sample (heavy on CPU)")
    ld.add_argument("--risk-limit", type=int, default=500, help="offenders to score when --with-risk")
    ld.set_defaults(func=_cmd_load_derived)

    vf = sub.add_parser("validate-fixtures",
                        help="read-only check that required derived-data fixtures exist "
                             "(non-zero exit if a required table is empty)")
    vf.set_defaults(func=_cmd_validate_fixtures)

    # ---- graph jobs (Phase 6) ----
    eg = sub.add_parser("enrich-graph", help="add intermediary nodes + seeded hidden associations")
    eg.add_argument("--seed", type=int, default=42)
    eg.set_defaults(func=_cmd_enrich_graph)

    cm = sub.add_parser("communities", help="Louvain communities + gang precision/recall")
    cm.set_defaults(func=_cmd_communities)

    ce = sub.add_parser("centrality", help="PageRank + betweenness -> EntityGraph.Properties")
    ce.add_argument("--betweenness-k", type=int, default=400, help="sample size for approx betweenness")
    ce.set_defaults(func=_cmd_centrality)

    ha = sub.add_parser("hidden-associations", help="materialize drishti_hidden_associations")
    ha.add_argument("--min-links", type=int, default=2)
    ha.set_defaults(func=_cmd_hidden_associations)

    # ---- geospatial jobs (Phase 7) ----
    lc = sub.add_parser("load-curated-case",
                        help="load the curated public-source case record (real case "
                             "from published court records) through the FIR intake "
                             "path; read-only and excluded from derived analytics")
    lc.add_argument("--actor", default="curated.loader")
    lc.set_defaults(func=_cmd_load_curated_case)

    hs = sub.add_parser("hotspots", help="ST-DBSCAN + KDE hotspots -> CrimeHotspot")
    hs.add_argument("--eps-m", type=float, default=1500.0)
    hs.add_argument("--eps-days", type=float, default=150.0)
    hs.add_argument("--min-samples", type=int, default=15)
    hs.set_defaults(func=_cmd_hotspots)

    ea = sub.add_parser("emerging-alerts", help="threshold-breach alerts -> AlertHistory")
    ea.add_argument("--window", type=int, default=6)
    ea.add_argument("--threshold-sigma", type=float, default=2.0)
    ea.set_defaults(func=_cmd_emerging_alerts)

    gv = sub.add_parser("geo-validate", help="PAI/hit-rate + known-pattern checks")
    gv.add_argument("--cutoff", default="2025-01-01")
    gv.set_defaults(func=_cmd_geo_validate)

    # ---- risk scoring (Phase 9) ----
    rs = sub.add_parser("risk-score", help="TabFM offender risk -> CrimeRiskScore")
    rs.add_argument("--context-size", type=int, default=1000)
    rs.add_argument("--limit", type=int, default=None, help="score a stratified sample (for heavy CPU models)")
    rs.add_argument("--estimators", type=int, default=None, help="TabFM ensemble members")
    rs.set_defaults(func=_cmd_risk_score)

    rc = sub.add_parser("risk-calibration", help="foundation vs baseline calibration report")
    rc.set_defaults(func=_cmd_risk_calibration)

    # ---- case decision-support (Phase 10) ----
    ec = sub.add_parser("embed-cases", help="embed a case corpus -> CrimeEmbedding (similar-case search)")
    ec.add_argument("--limit", type=int, default=12000,
                    help="cases to embed, stratified by sub-head (0 = all)")
    ec.add_argument("--batch-size", type=int, default=512)
    ec.add_argument("--embedder", default=None, help="mpnet|st|hashing (default: auto)")
    ec.set_defaults(func=_cmd_embed_cases)

    cs = sub.add_parser("case-summary", help="generate + write a cited AISummary for one case")
    cs.add_argument("--case", type=int, required=True)
    cs.set_defaults(func=_cmd_case_summary)

    cl = sub.add_parser("case-leads", help="generate + write ranked OfficerRecommendation leads for one case")
    cl.add_argument("--case", type=int, required=True)
    cl.set_defaults(func=_cmd_case_leads)

    # ---- money-trail detection (Phase 11) ----
    md = sub.add_parser("money-detect", help="flag structuring/layering/circular -> FinancialTransaction + AlertHistory")
    md.add_argument("--structuring-min-count", type=int, default=5)
    md.add_argument("--structuring-window-days", type=int, default=14)
    md.add_argument("--cycle-min-amount", type=float, default=10000)
    md.add_argument("--cycle-max-len", type=int, default=6)
    md.set_defaults(func=_cmd_money_detect)

    # ---- forecasting + early warning (Phase 12) ----
    fr = sub.add_parser("forecast-run", help="run TabFM+TimesFM+near-repeat+ST-GNN, fuse -> CrimePrediction + alerts")
    fr.add_argument("--head-id", type=int, default=None)
    fr.add_argument("--horizon-days", type=int, default=30)
    fr.set_defaults(func=_cmd_forecast_run)

    fv = sub.add_parser("forecast-validate", help="PAI/hit-rate on held-out incidents per district & head")
    fv.add_argument("--cutoff", default=None, help="YYYY-MM-DD")
    fv.add_argument("--horizon-months", type=int, default=3)
    fv.add_argument("--area-fraction", type=float, default=0.25)
    fv.set_defaults(func=_cmd_forecast_validate)

    fb = sub.add_parser("forecast-backtest",
                        help="rolling-origin backtest: MAE/RMSE/WAPE/sMAPE + coverage + baselines "
                             "+ geographic holdout -> ForecastBacktest")
    fb.add_argument("--head-id", type=int, default=None)
    fb.add_argument("--horizon", type=int, default=1)
    fb.add_argument("--n-origins", type=int, default=6)
    fb.add_argument("--no-per-head", action="store_true", help="skip the per-crime-head breakdown")
    fb.add_argument("--no-persist", action="store_true", help="do not write a ForecastBacktest row")
    fb.set_defaults(func=_cmd_forecast_backtest)

    # ---- aggregate station-workload band (Phase 13) ----
    we = sub.add_parser("workload-eval",
                        help="held-out evaluation of the aggregate station case-review workload "
                             "band task: metrics + calibration + baselines + geo holdout + leakage")
    we.add_argument("--foundation", default="incontext", help="incontext|tabpfn|tabfm|auto")
    we.set_defaults(func=_cmd_workload_eval)

    wr = sub.add_parser("workload-run",
                        help="persist a governed workload run: FeatureSnapshot + PredictionResult "
                             "per station, register the approved model + training snapshot")
    wr.add_argument("--foundation", default="incontext", help="incontext|tabpfn|tabfm|auto")
    wr.add_argument("--limit", type=int, default=None, help="cap stations persisted")
    wr.add_argument("--lifecycle", default="staged",
                    choices=["staged", "shadow", "active", "retired"])
    wr.set_defaults(func=_cmd_workload_run)

    wb = sub.add_parser("workload-benchmark",
                        help="500/5,000/full-row benchmark grid (runtime/memory/latency/cost/"
                             "metrics vs baselines) -> ModelBenchmark")
    wb.add_argument("--heavy", action="store_true",
                    help="include the real TabFM/TabPFN weights (slow on CPU)")
    wb.set_defaults(func=_cmd_workload_benchmark)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
