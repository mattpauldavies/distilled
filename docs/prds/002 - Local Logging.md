# Local Logging

## 💼 Summary

Add lightweight local logging in development mode that writes recent application logs to a local file (git ignored) to improve debugging and developer experience.

This feature is strictly for **local development** and must not affect production logging behaviour.

---

## 🎯 Goals

- Make it easier to debug issues locally without relying solely on console output.
- Persist recent logs to a local file for inspection after crashes or restarts.
- Ensure zero impact on production behaviour.

## 🚫 Non-goals

- Replacing existing production logging or observability.
- Implementing log aggregation, rotation infrastructure, or structured log shipping.
- Adding complex logging configuration.

---

## 🧩 Functional Requirements

### 1️⃣ Development-only behaviour

- Logging to a local file must be enabled **only when `NODE_ENV=development`** (or equivalent environment flag).
- In production environments, this feature must be disabled by default.

### 2️⃣ Log file location

- Logs must be written to a file inside a directory such as:
  - `/logs/dev.log` or similar

- The directory and file must be added to `.gitignore`.

### 3️⃣ Log content

- The file should capture:
  - Application-level logs (info, warn, error)
  - Relevant request/response metadata (where applicable)

- Logs should remain human-readable (plain text is acceptable; structured JSON optional).

### 4️⃣ Log size management

- The file should:
  - Either truncate on application start, OR
  - Maintain a simple rolling “tail” behaviour.

---

## 🛠 Implementation Guidelines

- Reuse existing logging abstraction if one exists.
- If no abstraction exists, introduce a minimal logger wrapper that:
  - Writes to console (existing behaviour)
  - Conditionally writes to file in development mode

- Feel free to add logging dependencies if it will give a meaningful improvement to developer experience.

---

## ✅ Acceptance Criteria

- When running the app locally in development:
  - A log file is created automatically.
  - Logs are written to the file as the app runs.
  - The log file is not tracked by git.

- When running in production mode:
  - No local log file is written.
  - Existing logging behaviour remains unchanged. (We still log to stdout)

- Developers can inspect the file after a crash or error to see recent logs.

---

## 📈 Success Criteria

- Developers report faster debugging when reproducing issues locally.
- No regressions or behavioural differences between development and production modes.
