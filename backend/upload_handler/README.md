# File upload

Accepts authenticated multipart CSV/XLSX uploads through `/api/upload`, validates size and format, and stores them using the configured object-store adapter. Returns the existing `fileId`, `columns`, `rowCount`, `filename` and `fileType` response fields. The parser enforces bounds before model work begins.

See the root README for local setup, limits and tests.
