# Legacy prototype (reference only — NOT part of the running app)

This is the earlier React Native (JavaScript) prototype, kept unmodified so nothing built before is lost. It talks to the retired Node/Express
API (`http://localhost:4000`, JWT + Supabase-style `apiRequest`) and runs AI classification client-side; both are **superseded** by the
FastAPI backend, and no second backend is shipped. Metro never bundles it (nothing under `app/` or `src/` imports it).

What was carried into the new TypeScript app (`../app`, `../src`): brand assets, the 7-language dictionary (identical file, drift-tested),
permission wording, and the screen set — Home, Report/Complaint, Tracking, Chatbot (→ Copilot), Heatmap (→ Map), Case Analyzer (→ Legal),
RTI, Emergency, Settings/Privacy, Notifications, Auth (with 2-factor via the API).

Not yet ported (ideas for follow-up, each needs a backend contract first): Document Scanner (on-device ML Kit OCR; the server-side OCR now exists),
Civic Locator, Department Directory, Official Portal, Interoperability/Monitoring/Fragmentation diagnostics.
