# DRISHTI — Catalyst Console setup guide (Prompt 23)

> **Auto-generated** by `infra/catalyst/ds-schema/generate_console_guide.py` from the repo's authoritative schemas. Data Store tables and Stratus buckets can **only** be created in the Catalyst Console (no SDK/API/CLI — confirmed by Catalyst docs), so this is the exact, minimal manual checklist. Everything else (data import, deploy, verification) is automated by Kiro.

**Project:** DHRISTI `48361000000030003`, org `60075362708`, India DC, Development.

## Column conventions

- Catalyst auto-adds `ROWID`, `CREATORID`, `CREATEDTIME`, `MODIFIEDTIME` to every table — do **not** add those.
- Add **`ExternalID`** (Varchar, **Unique**, Mandatory) to every table — it is the idempotent-upsert key Kiro's `ds:import` uses.
- Type mapping used below: int→**BigInt**, text→**Varchar**, bigtext→**Text**, bool→**Boolean**, numeric→**Double**, json→**Text**, timestamp→**DateTime**.

---

## Step 1 — Stratus buckets (Console → Stratus → Create Bucket)

Create 3 **private, versioned** buckets, then give the names to Kiro:

| Logical | Suggested name | Visibility | Versioning |
|---|---|---|---|
| evidence | `drishti-evidence` | Private | On |
| import | `drishti-import` | Private | On |
| report | `drishti-report` | Private | On |

---

## Step 2 — MVP Data Store tables (proves the full live path)

Create these first. `State` is the readiness probe; the 6 Board tables are Data Store-native and the app writes them live (no import needed) — this alone proves Auth → Gateway → AppSail → Data Store → Stratus. `PredictionRequest` is the trigger table for the ONE mandatory Signal (a `row_inserted` with `state='approved'` fires `prediction_event`).

> **Live-journey scope (honest):** Board + Disaster are Data Store-native and run live on the AppSail. The FIR/case/evidence-metadata/chat transactional flows are **postgres-backed** (analytics plane) and the operational AppSail is intentionally denied a `DATABASE_URL`, so those run in the local full-stack, not on the deployed AppSail. The deployed demo proves the Data Store-native operational journeys + evidence-file upload (Stratus) + the auth/gateway/security chain.

### `State`

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ExternalID` | Varchar (Unique, Mandatory) | yes |
| `Active` | Boolean | no |
| `NationalityID` | BigInt | no |
| `StateID` | BigInt | no |
| `StateName` | Varchar | no |

### `InvestigationBoard`  (PK: `BoardID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `BoardID` | BigInt | yes |
| `Title` | Varchar | yes |
| `Description` | Text | no |
| `OwnerActor` | Varchar | yes |
| `OwnerEmployeeID` | BigInt | no |
| `CaseMasterID` | BigInt | no |
| `UnitID` | BigInt | no |
| `DistrictID` | BigInt | no |
| `Status` | Varchar | yes |
| `Visibility` | Varchar | yes |
| `IsLocked` | Boolean | yes |
| `Version` | BigInt | yes |
| `ParentBoardID` | BigInt | no |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

### `BoardNode`  (PK: `BoardNodeID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `BoardNodeID` | BigInt | yes |
| `BoardID` | BigInt | yes |
| `NodeKind` | Varchar | yes |
| `RefTable` | Varchar | no |
| `RefID` | Varchar | no |
| `CanonicalEntityID` | BigInt | no |
| `Label` | Varchar | no |
| `PosX` | Double | yes |
| `PosY` | Double | yes |
| `Width` | Double | no |
| `Height` | Double | no |
| `StyleJSON` | Text | no |
| `SnapshotJSON` | Text | no |
| `SourceVersion` | Varchar | no |
| `SourceHash` | Varchar | no |
| `CreatedBy` | Varchar | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `BoardEdge`  (PK: `BoardEdgeID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `BoardEdgeID` | BigInt | yes |
| `BoardID` | BigInt | yes |
| `SourceNodeID` | BigInt | yes |
| `TargetNodeID` | BigInt | yes |
| `EdgeClass` | Varchar | yes |
| `Label` | Varchar | no |
| `RelationshipType` | Varchar | no |
| `Directed` | Boolean | yes |
| `Confidence` | Double | no |
| `Rationale` | Text | no |
| `EvidenceCaseID` | BigInt | no |
| `SourceRecordID` | Varchar | no |
| `StyleJSON` | Text | no |
| `PromotedStatus` | Varchar | no |
| `PromotedRef` | Varchar | no |
| `CreatedBy` | Varchar | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `BoardAnnotation`  (PK: `BoardAnnotationID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `BoardAnnotationID` | BigInt | yes |
| `BoardID` | BigInt | yes |
| `Kind` | Varchar | yes |
| `Content` | Text | no |
| `GeometryJSON` | Text | no |
| `StyleJSON` | Text | no |
| `CreatedBy` | Varchar | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `BoardCollaborator`  (PK: `BoardCollaboratorID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `BoardCollaboratorID` | BigInt | yes |
| `BoardID` | BigInt | yes |
| `Actor` | Varchar | yes |
| `EmployeeID` | BigInt | no |
| `Role` | Varchar | yes |
| `AddedBy` | Varchar | yes |
| `AddedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `BoardActivity`  (PK: `BoardActivityID`, append-only)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `BoardActivityID` | BigInt | yes |
| `BoardID` | BigInt | yes |
| `Actor` | Varchar | yes |
| `Action` | Varchar | yes |
| `TargetType` | Varchar | no |
| `TargetID` | Varchar | no |
| `DiffJSON` | Text | no |
| `RequestID` | Varchar | no |
| `CreatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

### `PredictionRequest`  (PK: `PredictionRequestID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `PredictionRequestID` | Varchar | yes |
| `state` | Varchar | yes |
| `task` | Varchar | no |
| `requested_backend` | Varchar | no |
| `idempotency_key` | Varchar | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

---

## Step 3 — Reference tables (for Ask DRISHTI / dashboard reads)

Create these to serve real read data; Kiro then imports the rows (`ds:import`, idempotent by `ExternalID`).

### `District`

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ExternalID` | Varchar (Unique, Mandatory) | yes |
| `Active` | Boolean | no |
| `DistrictID` | BigInt | no |
| `DistrictName` | Varchar | no |
| `StateID` | BigInt | no |

### `CaseCategory`

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ExternalID` | Varchar (Unique, Mandatory) | yes |
| `CaseCategoryID` | BigInt | no |
| `LookupValue` | Varchar | no |

### `CaseStatusMaster`

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ExternalID` | Varchar (Unique, Mandatory) | yes |
| `CaseStatusID` | BigInt | no |
| `CaseStatusName` | Varchar | no |

### `Unit`

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ExternalID` | Varchar (Unique, Mandatory) | yes |
| `Active` | Boolean | no |
| `DistrictID` | BigInt | no |
| `NationalityID` | BigInt | no |
| `ParentUnit` | Varchar | no |
| `StateID` | BigInt | no |
| `TypeID` | BigInt | no |
| `UnitID` | BigInt | no |
| `UnitName` | Varchar | no |

### `Employee`

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ExternalID` | Varchar (Unique, Mandatory) | yes |
| `AppointmentDate` | DateTime | no |
| `BloodGroupID` | BigInt | no |
| `DesignationID` | BigInt | no |
| `DistrictID` | BigInt | no |
| `EmployeeDOB` | DateTime | no |
| `EmployeeID` | BigInt | no |
| `FirstName` | Varchar | no |
| `GenderID` | BigInt | no |
| `KGID` | BigInt | no |
| `PhysicallyChallenged` | Varchar | no |
| `RankID` | BigInt | no |
| `UnitID` | BigInt | no |

### `CaseMaster`

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ExternalID` | Varchar (Unique, Mandatory) | yes |
| `BriefFacts` | Text | no |
| `BriefFactsFTS` | Text | no |
| `CaseCategoryID` | BigInt | no |
| `CaseMasterID` | BigInt | no |
| `CaseNo` | Varchar | no |
| `CaseStatusID` | BigInt | no |
| `CourtID` | BigInt | no |
| `CrimeMajorHeadID` | BigInt | no |
| `CrimeMinorHeadID` | BigInt | no |
| `CrimeNo` | Varchar | no |
| `CrimeRegisteredDate` | DateTime | no |
| `GravityOffenceID` | BigInt | no |
| `IncidentFromDate` | DateTime | no |
| `IncidentToDate` | DateTime | no |
| `InfoReceivedPSDate` | DateTime | no |
| `PolicePersonID` | BigInt | no |
| `PoliceStationID` | BigInt | no |
| `latitude` | Double | no |
| `longitude` | Double | no |

_Excluded (PostGIS geometry, not supported in Data Store): `geom` — the app derives lat/long separately._

---

## Step 4 — Disaster Response tables (optional journey, 14 tables)

Data Store-native; the app seeds golden rows at runtime. Create if you want the Disaster demo.

### `HazardType`  (PK: `HazardTypeID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `HazardTypeID` | BigInt | yes |
| `Code` | Varchar | yes |
| `Name` | Varchar | yes |
| `Category` | Varchar | no |
| `DefaultLeadTimeHours` | BigInt | no |
| `Active` | Boolean | yes |
| `CreatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

### `FeedSource`  (PK: `FeedSourceID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `FeedSourceID` | BigInt | yes |
| `Code` | Varchar | yes |
| `Name` | Varchar | yes |
| `Provider` | Varchar | no |
| `ConnectorKind` | Varchar | yes |
| `Licence` | Varchar | no |
| `Attribution` | Varchar | no |
| `FreshnessSlaMinutes` | BigInt | no |
| `ExternalAccessRequired` | Boolean | yes |
| `CreatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

### `Resource`  (PK: `ResourceID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ResourceID` | BigInt | yes |
| `ResourceType` | Varchar | yes |
| `Name` | Varchar | yes |
| `Quantity` | BigInt | yes |
| `Unit` | Varchar | no |
| `HomeUnitID` | BigInt | no |
| `EmployeeID` | BigInt | no |
| `Lon` | Double | no |
| `Lat` | Double | no |
| `Capacity` | BigInt | no |
| `Capabilities` | Text | no |
| `Status` | Varchar | yes |
| `DistrictID` | BigInt | no |
| `Version` | BigInt | yes |
| `LastUpdatedAt` | DateTime | yes |
| `CreatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `ReliefShelter`  (PK: `ReliefShelterID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ReliefShelterID` | BigInt | yes |
| `Name` | Varchar | yes |
| `Lon` | Double | no |
| `Lat` | Double | no |
| `DistrictID` | BigInt | no |
| `Capacity` | BigInt | yes |
| `CurrentOccupancy` | BigInt | yes |
| `Facilities` | Text | no |
| `Status` | Varchar | yes |
| `Version` | BigInt | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `HazardEvent`  (PK: `HazardEventID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `HazardEventID` | BigInt | yes |
| `HazardCode` | Varchar | yes |
| `Status` | Varchar | yes |
| `Severity` | Varchar | yes |
| `DistrictID` | BigInt | no |
| `UnitID` | BigInt | no |
| `GeoJSON` | Text | no |
| `CanonicalCRS` | Varchar | no |
| `CentroidLon` | Double | no |
| `CentroidLat` | Double | no |
| `OnsetAt` | DateTime | no |
| `PredictedPeakAt` | DateTime | no |
| `Source` | Varchar | no |
| `SourceVersion` | Varchar | no |
| `Description` | Text | no |
| `Version` | BigInt | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `HydroMetReading`  (PK: `HydroMetReadingID`, append-only)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `HydroMetReadingID` | BigInt | yes |
| `StationCode` | Varchar | yes |
| `SourceAgency` | Varchar | no |
| `MetricType` | Varchar | yes |
| `Value` | Double | no |
| `Unit` | Varchar | no |
| `Lon` | Double | no |
| `Lat` | Double | no |
| `DistrictID` | BigInt | no |
| `ObservedAt` | DateTime | yes |
| `ReceivedAt` | DateTime | yes |
| `QualityFlag` | Varchar | yes |
| `SourceRecordID` | Varchar | no |
| `IngestionRunID` | Varchar | no |
| `FeedCode` | Varchar | no |
| `SupersededByID` | BigInt | no |
| `CreatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

### `HazardRiskZone`  (PK: `HazardRiskZoneID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `HazardRiskZoneID` | BigInt | yes |
| `HazardCode` | Varchar | yes |
| `ZoneKind` | Varchar | yes |
| `Name` | Varchar | no |
| `DistrictID` | BigInt | no |
| `GeoJSON` | Text | no |
| `CentroidLon` | Double | no |
| `CentroidLat` | Double | no |
| `RiskLevel` | Varchar | yes |
| `Score` | Double | no |
| `Factors` | Text | no |
| `ValidFrom` | DateTime | no |
| `ValidTo` | DateTime | no |
| `Source` | Varchar | no |
| `SourceVersion` | Varchar | no |
| `IsActive` | Boolean | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `HazardPrediction`  (PK: `HazardPredictionID`, append-only)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `HazardPredictionID` | BigInt | yes |
| `HazardCode` | Varchar | yes |
| `HazardEventID` | BigInt | no |
| `ModelVersionLabel` | Varchar | no |
| `FeatureSnapshotID` | Varchar | no |
| `DistrictID` | BigInt | no |
| `UnitID` | BigInt | no |
| `GeoJSON` | Text | no |
| `ForecastStart` | DateTime | no |
| `ForecastEnd` | DateTime | no |
| `HorizonHours` | BigInt | no |
| `DataAsOf` | DateTime | no |
| `Probability` | Double | no |
| `PredictedSeverity` | Varchar | no |
| `ExpectedImpact` | Text | no |
| `Confidence` | Double | no |
| `Factors` | Text | no |
| `BaselineComparison` | Text | no |
| `QualityState` | Varchar | yes |
| `SupersededByID` | BigInt | no |
| `CreatedBy` | Varchar | no |
| `CreatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

### `ResourceAllocation`  (PK: `ResourceAllocationID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ResourceAllocationID` | BigInt | yes |
| `HazardEventID` | BigInt | no |
| `ResourceID` | BigInt | no |
| `TargetZoneID` | BigInt | no |
| `QuantityAllocated` | BigInt | yes |
| `Status` | Varchar | yes |
| `Score` | Double | no |
| `Reason` | Text | no |
| `ProposedByActor` | Varchar | no |
| `ApprovedByActor` | Varchar | no |
| `ApprovedByEmployeeID` | BigInt | no |
| `DistrictID` | BigInt | no |
| `ProposedAt` | DateTime | no |
| `ApprovedAt` | DateTime | no |
| `DispatchedAt` | DateTime | no |
| `EnrouteAt` | DateTime | no |
| `OnsiteAt` | DateTime | no |
| `ReleasedAt` | DateTime | no |
| `Version` | BigInt | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `EvacuationRoute`  (PK: `EvacuationRouteID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `EvacuationRouteID` | BigInt | yes |
| `HazardEventID` | BigInt | no |
| `FromZoneID` | BigInt | no |
| `ToShelterID` | BigInt | no |
| `GeoJSON` | Text | no |
| `DistanceKm` | Double | no |
| `EstMinutes` | Double | no |
| `RoadGraphVersion` | Varchar | no |
| `HazardExclusionVersion` | Varchar | no |
| `Status` | Varchar | yes |
| `Notes` | Text | no |
| `Version` | BigInt | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `ResponsePlan`  (PK: `ResponsePlanID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ResponsePlanID` | BigInt | yes |
| `HazardEventID` | BigInt | no |
| `HazardCode` | Varchar | yes |
| `Title` | Varchar | yes |
| `TemplateCode` | Varchar | no |
| `Status` | Varchar | yes |
| `DistrictID` | BigInt | no |
| `Version` | BigInt | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `ResponseTask`  (PK: `ResponseTaskID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `ResponseTaskID` | BigInt | yes |
| `ResponsePlanID` | BigInt | yes |
| `Title` | Varchar | yes |
| `Sequence` | BigInt | yes |
| `AssignedToActor` | Varchar | no |
| `AssignedToEmployeeID` | BigInt | no |
| `Status` | Varchar | yes |
| `DueAt` | DateTime | no |
| `CompletedAt` | DateTime | no |
| `Version` | BigInt | yes |
| `CreatedAt` | DateTime | yes |
| `UpdatedAt` | DateTime | yes |
| `DeletedAt` | DateTime | no |
| `ExternalID` | Varchar (**Unique**) | yes |

### `FeedIngestionRun`  (PK: `FeedIngestionRunID`)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `FeedIngestionRunID` | BigInt | yes |
| `FeedSourceID` | BigInt | no |
| `FeedCode` | Varchar | yes |
| `StartedAt` | DateTime | yes |
| `FinishedAt` | DateTime | no |
| `Status` | Varchar | yes |
| `AcceptedCount` | BigInt | yes |
| `DuplicateCount` | BigInt | yes |
| `RejectedCount` | BigInt | yes |
| `LastObservedAt` | DateTime | no |
| `Detail` | Text | no |
| `CreatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

### `DisasterActivity`  (PK: `DisasterActivityID`, append-only)

| Column | Catalyst type | Mandatory |
|---|---|---|
| `DisasterActivityID` | BigInt | yes |
| `SubjectType` | Varchar | yes |
| `SubjectID` | Varchar | yes |
| `Actor` | Varchar | yes |
| `Action` | Varchar | yes |
| `DiffJSON` | Text | no |
| `RequestID` | Varchar | no |
| `CreatedAt` | DateTime | yes |
| `ExternalID` | Varchar (**Unique**) | yes |

---

## Step 5 — hand back to Kiro

Tell Kiro the **3 bucket names** and the **API Gateway URL**. Kiro then: sets function env, imports reference/operational rows, builds + deploys the frontend to Slate, and runs the full live verification (six roles, Signal + cron, Data Store/Stratus checks, CORS/replay/bypass) with evidence.

Non-table Console items are listed in `docs/deployment/CATALYST_LIVE_INVENTORY.md` §3 (AppSail env from `infra/catalyst/secrets/appsail-env.local.json`, API Gateway routes, Auth users, Signals rule, cron).
