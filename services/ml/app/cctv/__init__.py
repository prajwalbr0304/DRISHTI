"""CCTV monitoring: video-analytics alert review + nearest-station dispatch.

Pipeline (each arrow is a separate, audited API call — nothing chains itself):

    detector  ->  CctvDetection (append-only, carries provenance + confidence)
              ->  CctvAlert     Status='proposed'         [never active]
    analyst   ->  confirm (confirm=true, else 428)        -> Status='confirmed'
              or  dismiss (with a recorded reason)        -> Status='dismissed'
    system    ->  CctvDispatch  Status='proposed'         [nearest station, ranked]
    analyst   ->  dispatch (confirm=true, else 428)       -> Status='dispatched'

The module deliberately mirrors ``app/disaster`` file-for-file (repo/guards/
schemas/service/router/seed) so the review, audit, scope and confirmation
behaviour is identical to the Emergency Response surface already in the product.
"""
