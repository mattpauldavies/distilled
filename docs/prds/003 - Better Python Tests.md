# Better Python Tests

## 💼 Summary

Create a suite of Python tests that follow best practices and successfully test the existing code in `server/app`.
We have some tests already but we need more complete coverage.
We need to establish robust patterns that future tests can follow.
In the future we want to follow red->green development best practices.

---

## 🎯 Goals

- Write a robust suite of Python tests for the code in `server/app`

## 🚫 Non-goals

- Don't worry about `client` for now, we'll tackle that later

---

## 🛠 Implementation Guidelines

- Tests must cover all major scenarios
- Coverage should be >=90%
- Optimise for integration style tests that check how components work rather that unit tests which can be too isolated
- Optimise for simplicity and readability
- Remember that testing core use cases well is better than over-fitting tests to boost coverage

---

## ✅ Acceptance Criteria

- We have a simple Make command for running the tests
- We have a suite of functional tests
- Coverage is at an acceptable level
- We have not over-fitted and the tests are not fragile
