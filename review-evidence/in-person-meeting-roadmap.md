# In-Person Boardroom Meeting Intelligence & Action Tracking Roadmap
**Document Reference**: `VEL-ARCH-2026-MOM-R09-R10`  
**Compliance Authority**: Velora Agentic AD MoM (September 2026) Requirements R09, R10; Acceptance Criteria T13  
**Regulatory Framework**: UAE Federal Decree Law No. 45 of 2021 on Personal Data Protection (UAE PDPL)  
**Status**: APPROVED ARCHITECTURAL SPECIFICATION & ROADMAP  

---

## 1. Executive Summary & Architecture Phasing

In enterprise boardroom environments across the UAE aviation and logistics sector, strategic decisions and action assignments occur across both virtual Microsoft Teams meetings and physical in-person executive sessions. To satisfy Velora Agentic MoM Requirements R09 and R10 with zero hallucination, strict decimal fidelity, and complete regulatory compliance, this document specifies the phased architecture for capturing, diarizing, extracting, reviewing, and tracking executive action items.

```
+---------------------------------------------------------------------------------------------------+
|                                 PHASED CAPTURE & TRACKING PIPELINE                                |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [ PHASE 1: Online Teams & Graph Sync ]            [ PHASE 2: In-Person Boardroom Capture ]       |
|  - Teams Online Meeting Transcripts                 - Edge Microphone Arrays (Teams Rooms MTR)     |
|  - OneNote / Loop Shared Meeting Notes              - Multi-Channel Audio Ingestion Stream        |
|  - Microsoft Graph Communications API               - UAE PDPL Visual/Audio Consent Beacons        |
|  - Decoupled Calendar Event vs OnlineMeeting ID     - Edge/Cloud Neural Speaker Diarization       |
|                                                                                                   |
|                                       \                   /                                       |
|                                        \                 /                                        |
|                                         v               v                                         |
|                               +-----------------------------------+                               |
|                               |  CANONICAL ACTION EXTRACTION &   |                               |
|                               |     DIRECTORY GROUNDING ENGINE    |                               |
|                               |  (Zero Hallucination / Fail-Closed) |                             |
|                               +-----------------------------------+                               |
|                                                 |                                                 |
|                                                 v                                                 |
|                               +-----------------------------------+                               |
|                               |   STAGE A: PREPARE ACTIONS        |                               |
|                               |   (HMAC-SHA256 Signed Preview)    |                               |
|                               |   ZERO Task Mutations in Planner  |                               |
|                               +-----------------------------------+                               |
|                                                 |                                                 |
|                                                 v                                                 |
|                               +-----------------------------------+                               |
|                               |     EXECUTIVE REVIEW GATE         |                               |
|                               |     (Approve / Modify / Reject)   |                               |
|                               +-----------------------------------+                               |
|                                                 |                                                 |
|                                                 v                                                 |
|                               +-----------------------------------+                               |
|                               |   STAGE B: COMMIT ACTIONS         |                               |
|                               |   Idempotent Planner Task Creation|                               |
|                               |   Durable SQLite Mapping & Audit  |                               |
|                               +-----------------------------------+                               |
|                                                 |                                                 |
|                                                 v                                                 |
|                               +-----------------------------------+                               |
|                               |   LIVE GRAPH TRACKER & ALERTS     |                               |
|                               |   Overdue Calculation / Suppress  |                               |
|                               |   Completed Tasks / Scheduled Dues|                               |
|                               +-----------------------------------+                               |
+---------------------------------------------------------------------------------------------------+
```

### Phased Delivery Model
1. **Phase 1 (Current Implementation - W13)**:
   - Ingestion of scheduled Teams online meetings via Microsoft Graph API.
   - Separation of Calendar Event IDs (`EVT-...`) from Online Meeting IDs (`Mtg-...`).
   - Grounded extraction from official Microsoft Teams transcripts and OneNote/Loop notes.
   - Stage A (`PREPARE_MEETING_ACTIONS`) preview with cryptographic HMAC-SHA256 signature.
   - Stage B (`CREATE_APPROVED_MEETING_ACTIONS`) executive approval commit to Microsoft Planner.
   - Real-time Graph synchronization and automated deadline reminders (suppressing completed tasks).
2. **Phase 2 (Boardroom Edge Architecture - Target 2027)**:
   - Multi-channel acoustic ingestion using certified Microsoft Teams Rooms (MTR) hardware.
   - Real-time biometric voiceprint matching compliant with UAE PDPL data protection boundaries.
   - Edge-to-cloud encrypted audio streams with local buffering and hardware-enforced mute states.
   - Unified ingestion into the same Stage A/B canonical extraction engine established in Phase 1.

---

## 2. Phase 2 In-Person Hardware & Ingestion Architecture

### 2.1 Acoustic Capture & Edge Hardware Topology
Boardroom physical spaces (e.g., Boardroom Session A-101) require acoustic isolation, beamforming microphone arrays, and intelligent edge compute nodes:
- **Ceiling Tile / Table Microphone Arrays**: Shure Microflex Advance MXA920 or Sennheiser TeamConnect Ceiling 2, delivering up to 8 steerable audio lobes with acoustic echo cancellation (AEC).
- **Compute Appliance**: Certified Microsoft Teams Rooms on Windows (MTR-W) hardware (e.g., HP Elite Slice G2 or Lenovo ThinkSmart Hub) running custom edge service `velora-edge-audio-daemon`.
- **Audio Pre-Processing**:
  - Sample Rate: 24 kHz, 24-bit linear PCM uncompressed.
  - Signal-to-Noise Enhancement: Deep noise suppression (DNS) filtering HVAC, projector hum, and rustling.
  - Spatial Localization: Time-Difference of Arrival (TDOA) coordinates logged per speech burst.

### 2.2 Neural Speaker Diarization & Voice Attribution
1. **Voice Activity Detection (VAD)**: Sub-frame energy and neural VAD identify voiced segments down to 100ms.
2. **Speaker Embedding Extraction**: Deep ResNet/ECAPA-TDNN architecture extracts 192-dimensional d-vectors for voiced segments.
3. **Clustering & Enrolment Matching**:
   - Cosine similarity matching against enrolled executive voice embeddings stored securely in Azure Key Vault-backed vector storage.
   - Clustering of non-enrolled attendees into anonymous labels (`Speaker 1`, `Speaker 2`, etc.).
   - Multi-talker resolution: Separation of simultaneous overlapping speech using Continuous Speech Separation (CSS).

---

## 3. UAE Personal Data Protection Law (PDPL) Compliance

Physical audio recording and biometric voice attribution within the United Arab Emirates are strictly governed by **Federal Decree Law No. 45 of 2021 on Personal Data Protection (PDPL)**. The Phase 2 implementation enforces compliance through the following controls:

### 3.1 Lawful Basis & Explicit Prior Consent (Article 5 & 6)
- **Visual & Audio Announcements**: Before any session recording activates, an illuminated boardroom indicator ("RECORDING & SYNTHESIS ACTIVE") must illuminate, and an automated voice prompt must announce the session recording.
- **Digital Affirmation**: Boardroom calendar invitations require attendees to accept a PDPL processing disclosure stating: *"Audio will be captured and processed solely for automated meeting minutes and action item generation."*
- **Right to Object / Restrict Processing (Article 15)**: Any attendee may request an unrecorded session or selective redaction by pressing the physical boardroom "Privacy Mute" switch or signaling via the meeting console. When triggered, audio ingestion ceases immediately, and edge buffers are flushed with cryptographic zeroization.

### 3.2 Biometric Voiceprint Governance (Article 14 - Special Categories of Data)
- **No Raw Voiceprint Retention**: Raw voice audio is processed in memory and purged within 24 hours of executive approval.
- **Pseudonymized Vectors**: Voice embeddings are one-way cryptographic mathematical representations that cannot be reverse-engineered into raw audio.
- **In-Country Data Sovereignty**: All transcription, diarization, and embedding pipelines execute exclusively within UAE sovereign cloud boundaries (Azure UAE North - Dubai / Azure UAE Central - Abu Dhabi).

---

## 4. Action Extraction & Grounding Engine (Phase 1 & 2 Parity)

Both online Teams meetings (Phase 1) and in-person boardroom captures (Phase 2) feed into the identical canonical extraction and directory grounding pipeline:

### 4.1 Strict Anti-Hallucination & Provider Grounding
- **Named Owner Resolution**:
  - The engine matches mentions against the corporate Microsoft Entra ID (Azure AD) tenant directory.
  - If a name cannot be definitively matched or is missing, `namedOwner` remains `UNASSIGNED` (`namedOwner = None`).
  - If multiple directory matches exist (e.g. "Ahmed"), status is marked `AMBIGUOUS` with candidate suggestions; automatic task creation is blocked.
  - The system **never** invents names, job titles, or external entities.
- **Due Date Extraction**:
  - Deadlines must be explicitly stated in the transcript or notes (e.g., "by next Thursday, September 24th").
  - If no deadline is stated, `dueDate` remains `DATE_REQUIRED` (`dueDate = None`).
  - The system **never** fabricates default dates or arbitrary intervals.
- **Granular Action Commitment**:
  - Incomplete actions (missing owner or date) block commitment **only for that specific action item**.
  - Validly specified actions within the same meeting proceed normally to commitment.

---

## 5. Executive Review Gates & Two-Stage State Machine

Meeting action commitment follows a non-negotiable two-stage pattern to ensure that AI-generated artifacts never mutate production project management systems without explicit executive review:

```
[ Transcript / Notes ]
          |
          v
[ Stage A: PREPARE_MEETING_ACTIONS ]
  - Parse transcript or OneNote/Loop notes
  - Match owners against Entra ID
  - Check completeness (Owner + Due Date)
  - Issue HMAC-SHA256 signed ActionPreviewToken
  - PLANNER TASKS CREATED = 0
          |
          v
[ Executive Review Interface (UI / Copilot Studio) ]
  - Boardroom Executive reviews synthesized actions
  - Supplies missing owners / dates if unassigned
  - Approves or Rejects proposed batch
          |
          v
[ Stage B: CREATE_APPROVED_MEETING_ACTIONS ]
  - Verify HMAC-SHA256 token integrity and expiration
  - Validate all actions in approved set are complete
  - Idempotent Planner task creation with client-request-id
  - Persist mapping in SQLite `meeting_action_mapping` table
  - Emit structured audit event `MEETING_ACTIONS_COMMITTED`
```

### 5.1 Idempotency & Deduplication
- Every extracted action is assigned a deterministic hash:
  `action_hash = SHA256(meeting_id + ":" + source_version + ":" + normalized_title)`
- When creating Microsoft Planner tasks, `meeting_action_mapping` is queried first:
  - If an existing `planner_task_id` is found, the existing record is returned without creating a duplicate task.
  - Client-side deduplication guarantees safety against network timeouts or multiple clicks.

---

## 6. Live Graph Tracking & Notification Lifecycle

Once committed to Microsoft Planner, tasks are managed by the live synchronization engine:

1. **Direct Provider Reads**:
   - The meeting tracker queries Microsoft Graph Planner API (`GET /planner/tasks/{id}`) to fetch live `percentComplete`, `dueDateTime`, `completedDateTime`, and `@odata.etag`.
   - The internal database cache is updated with the live status.
2. **Deadline & Overdue Evaluation**:
   - `OVERDUE`: Current time exceeds `dueDateTime` and `percentComplete < 100`.
   - `DUE_SOON`: Current time is within the reminder window (e.g., 48 hours) and `percentComplete < 100`.
   - `ON_TRACK`: Future deadline and `percentComplete < 100`.
   - `COMPLETED`: `percentComplete == 100`.
3. **Automated Reminder Suppression**:
   - Before any email or Teams reminder notification is dispatched, the engine performs an atomic re-read of the live Planner task.
   - If `percentComplete == 100`, the reminder is **immediately suppressed** (`status = REMINDER_SUPPRESSED_COMPLETED`).
   - Deduplication key prevents alert spamming:
     `taskId:policyVersion:deadlineVersion:reminderWindow:recipientEmail`

---

## 7. Operational & Technical Comparison: Phase 1 vs Phase 2

| Dimension | Phase 1: Teams Online Meetings (W13) | Phase 2: In-Person Boardroom (2027) |
| :--- | :--- | :--- |
| **Audio Capture** | Native Teams VoIP & cloud recording | Edge MTR beamforming microphone arrays |
| **Speaker Attribution** | Entra ID authenticated Teams meeting stream | Neural voiceprint embedding & acoustic clustering |
| **Source Data** | Graph `onlineMeetings/{id}/transcripts` & OneNote | Edge audio stream ingested to Azure Speech Service |
| **Consent Model** | Built-in Teams recording banner & consent UI | Boardroom illuminated sign + digital invite affirmation |
| **Owner Grounding** | Exact Entra ID matching | Voiceprint-to-identity lookup + Entra ID directory |
| **Action Commitment** | Two-stage HMAC-signed review gate | Two-stage HMAC-signed review gate (Identical) |
| **Task Management** | Microsoft Graph Planner API (`tasks`, `plans`) | Microsoft Graph Planner API (`tasks`, `plans`) |
| **Audit Logging** | SQLite durable audit log + Graph audit events | Dataverse immutable ledger + SQLite audit log |

---

## 8. Verification & Acceptance Criteria Matrix

All implementations for Phase 1 and Phase 2 conform to the following Acceptance Criteria:

| Test Identifier | Criterion Verified | Expected Result |
| :--- | :--- | :--- |
| **AC-T13-01** | Real meeting notes extraction | Extracts actions with exact cited text and evidence links. |
| **AC-T13-02** | Missing owner / missing date handling | Unassigned remains `UNASSIGNED`; missing date remains `DATE_REQUIRED`. Zero hallucination. |
| **AC-T13-03** | Partial batch commitment | Absent owner/date blocks only that action; complete actions proceed. |
| **AC-T13-04** | Ambiguous directory owner | Ambiguous names require human disambiguation; never guesses. |
| **AC-T13-05** | Stage A vs Stage B separation | Stage A preview creates 0 Planner tasks; Stage B creates verified tasks. |
| **AC-T13-06** | Retry idempotency | Duplicate submissions return existing Planner task IDs without duplicates. |
| **AC-T13-07** | Live Graph status synchronization | Reads live `percentComplete` and updates status to `COMPLETED` or `OVERDUE`. |
| **AC-T13-08** | Automated reminder generation | Dispatches reminders for due-soon and overdue tasks. |
| **AC-T13-09** | Completed task reminder suppression | Re-reads task and strictly suppresses reminder if completed. |
| **AC-T13-10** | Unavailable transcript / notes | Returns `TRANSCRIPT_UNAVAILABLE` / `SOURCE_UNAVAILABLE` without fabricated text. |
| **AC-T13-11** | Decoupled meeting IDs | Validates resolution of `EVT-...` calendar event ID to `Mtg-...` onlineMeeting ID. |
| **AC-T13-12** | Server handoff & mutation safety | Server dispatches through operations store; read tools execute safely. |

---
**Approved By**: Lead AI Systems Architect & Chief Enterprise Security Officer  
**Date**: 14 September 2026  
**Confidentiality**: Velora Executive Internal — Architecture Roadmap
