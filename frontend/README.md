# Frontend

Angular application for the provider-neutral Public Comment Analyzer. Use a supported Node version (see `.node-version` in the repository root).

```sh
npm ci
npm start
```

The dev server proxies `/api` to `http://127.0.0.1:8000`. Start the backend following the root README. Production builds are served by the application on the same origin:

```sh
npm run build:prod
npm test -- --watch=false --browsers=ChromeHeadless
```

The access password stays in memory only. Model credentials never enter the browser. Generated markdown uses Angular sanitization, and chart configuration is validated on the server. Changes must preserve WCAG 2.1 AA and label AI output as a draft.
