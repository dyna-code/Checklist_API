# China AI compliance checklist - backend

The frontend form has one required tick: **"我已阅读 Agent 创建及使用条例"** on the
Review tab. This backend owns what happens when it is ticked: it answers every
question in `China-AI-Compliance-Checklist-IT-Solution.docx` with **Yes** and
writes the filled document.

No pre-filling and no skip logic is applied - every question in every section
(A1-A7, B1-B3, C1-C2, D1-D3, E1-E3, F1-F3, G1-G3, H1, I1 = 26 questions) is
answered Yes.

## Layout

```
backend/
  compliance/
    catalog.py     question vocabulary, ballot-box glyphs, expected template shape
    generator.py   fills the DOCX template (pure python-docx, keeps formatting)
    service.py     acknowledgement state + document generation
    server.py      standard-library HTTP API
    cli.py         local helpers (serve / acknowledge)
  templates/       reviewed template, copied from the workspace root
  out/             generated state + documents, one folder per request
  tests/           end-to-end tests
  tools/           template inspector + generated-document verifier
```

No third-party packages are needed - `python-docx` and the standard library
are enough. Use the bundled interpreter:

```powershell
$py = "C:\Users\thg4szh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
cd backend
& $py -m compliance.cli serve --port 8099
```

## API

Tick the checkbox:

```http
POST /api/ai-requests/{requestId}/compliance/acknowledge
Content-Type: application/json

{ "termsAcknowledged": true, "actor": "THG4SZH" }
```

`200` response:

```json
{
  "requestId": "REQ-123",
  "termsAcknowledged": true,
  "acknowledgedBy": "THG4SZH",
  "acknowledgedAt": "2026-10-14T11:11:33+08:00",
  "answers": { "A1": "Yes", "A2": "Yes", "...": "Yes" },
  "document": {
    "name": "China-AI-Compliance-Checklist-IT-Solution-REQ-123.docx",
    "questionCount": 26,
    "problems": []
  },
  "documentUrl": "/api/ai-requests/REQ-123/compliance/checklist.docx"
}
```

Other routes:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/ai-requests/{id}/compliance` | current state; a request that was never acknowledged reports `termsAcknowledged: false` |
| `GET` | `/api/ai-requests/{id}/compliance/checklist.docx` | the generated document |
| `GET` | `/healthz` | liveness probe |

Calling `acknowledge` twice is idempotent. Sending
`{"termsAcknowledged": false}` clears the flag and keeps any document already
generated.

## Frontend hook-up

```jsx
onChange={(event) => {
  const termsAcknowledged = event.target.checked;
  fetch(`/api/ai-requests/${requestId}/compliance/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ termsAcknowledged, actor: currentUser }),
  })
    .then((response) => response.json())
    .then(setComplianceState);
}}
```

The browser talks to this service directly, so keep the CORS header in
`server.py` scoped to the portal origin instead of `*` once the host is fixed.

## Local checks

```powershell
& $py -m unittest discover -s tests -v                          # tests
& $py -m compliance.cli acknowledge --request-id REQ-DEMO        # generate one document
& $py tools\verify_generated.py `
    templates\China-AI-Compliance-Checklist-IT-Solution-v1.3.docx `
    out\REQ-DEMO\China-AI-Compliance-Checklist-IT-Solution-REQ-DEMO.docx
```

`verify_generated.py` prints the answer matrix, every cell that differs from
the template, and the font used by the ballot boxes. A correct run reports 26
changed cells (the Yes column only) and "every question answered Yes".

## Two things to decide before this goes live

1. **Answering every question "Yes" asserts compliance.** The checklist says a
   `No` must be recorded as a compliance gap with evidence, and AI-4 needs
   China AI Compliance Board review. A blanket Yes on a ticked checkbox is a
   legal assertion, not an assessment - consider keeping the generated file a
   draft that the assessor signs off.
2. **The template ignores the skip rules.** A3, A4, A5, A6 and A7 decide which
   sections apply; answering everything Yes marks sections such as C and D as
   compliant even when the source document says they should be N/A.
