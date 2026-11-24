# Job Board User Acceptance Test Report

## Test session

| Field | Details |
|---|---|
| Project | COMP3613 Job Board |
| Reference revision | `8ae7567` |
| Test date | 2026-11-24 |
| Tester | Not provided |
| Environment | Local repository; `python -m pytest tests -q` |
| Overall result | **Automated suite passed; manual UAT and tester sign-off are pending.** |

This report maps the repository's public acceptance criteria to current automated evidence. It is not a claim that a human tester completed the workflows. The test command completed with **155 passed**. Tests use isolated test fixtures; this run did not validate a deployed environment or production database.

## Test cases

### UAT-01 — Authentication and role identity

- **Preconditions:** Test users and test database are available.
- **Steps:** Submit valid credentials to the login flow; try invalid credentials; inspect the returned user details.
- **Expected:** Valid credentials authenticate, invalid credentials are rejected, and password material is not returned.
- **Result:** **Pass — automated evidence.**
- **Evidence:** `tests/test_integration.py::test_login`, `tests/test_scenario.py::test_api_login_seed_admin`, and password/authentication cases in `tests/test_unit.py`.

### UAT-02 — Graduate job browsing

- **Preconditions:** Listings exist in published, pending, expired, and current states.
- **Steps:** Request the public jobs endpoint and inspect the listings returned.
- **Expected:** Only published, non-expired jobs are available to graduates.
- **Result:** **Pass — automated evidence.**
- **Evidence:** `tests/test_listings_service.py::test_public_browsing_filters_status_and_deadline`, `tests/test_scenario.py::test_jobs_endpoint_returns_list`.

### UAT-03 — Employer submission and administrator review

- **Preconditions:** An employer and an administrator exist.
- **Steps:** Submit a listing as the employer; review it as an administrator; publish or reject it; inspect public visibility.
- **Expected:** New listings await review, only administrators can review them, and publication makes the listing available.
- **Result:** **Pass — automated evidence.**
- **Evidence:** `tests/test_listings_routes.py::test_complete_listing_review_cycle`, `tests/test_listings_service.py::test_new_listing_starts_pending`, `tests/test_listings_service.py::test_admin_can_review_pending_listing`.

### UAT-04 — Graduate subscriptions and publication notifications

- **Preconditions:** A published-eligible listing and eligible/ineligible graduate accounts exist.
- **Steps:** Subscribe eligible graduates, attempt subscription as an ineligible user, then publish a listing.
- **Expected:** Eligible graduates can subscribe; ineligible users are refused; subscribers receive the publication notification automatically.
- **Result:** **Pass — automated evidence.**
- **Evidence:** `tests/test_notifications.py::test_publication_notifies_subscribers_automatically_once`, `tests/test_notifications.py::test_ineligible_graduate_cannot_apply_or_subscribe`.

### UAT-05 — On-platform application submission

- **Preconditions:** An eligible graduate and an open, published collect-mode listing exist.
- **Steps:** Apply with a cover letter and resume; inspect the saved application and the graduate's application list.
- **Expected:** The application is stored once and starts at `submitted`; ineligible users cannot apply.
- **Result:** **Pass — automated evidence.**
- **Evidence:** `tests/test_applications_service.py::test_creation_starts_submitted`, `tests/test_notifications.py::test_ineligible_graduate_cannot_apply_or_subscribe`, `tests/test_notifications.py::test_complete_listing_and_application_workflow`.

### UAT-06 — Applicant visibility and ownership

- **Preconditions:** Two employers own separate listings with applications; an administrator is available.
- **Steps:** View applicants as the listing owner, another employer, and an administrator.
- **Expected:** Employers can view applicants only for their own listings; cross-employer access is forbidden. Administrator applicant viewing/export is a separate permission from status transitions.
- **Result:** **Pass — automated evidence for applicant viewing.**
- **Evidence:** `tests/test_applications_service.py::test_owner_can_view_listing_applicants`, `tests/test_applications_service.py::test_applicant_route_returns_403_for_cross_employer`, `tests/test_applications_service.py::test_admin_can_view_but_cannot_transition_applications`.

### UAT-07 — Status lifecycle, history, and notifications

- **Preconditions:** An application is in `submitted` and its listing owner is available.
- **Steps:** Make a legal transition as the listing owner; inspect current status, history, and applicant notifications. Try an invalid, unchanged, cross-employer, or administrator transition.
- **Expected:** Only legal owner transitions succeed. Successful transitions persist previous/new status, actor, and timestamp and notify the applicant. Failed or unauthorized transitions do not change status or create history/notifications.
- **Result:** **Pass — automated evidence.**
- **Evidence:** `tests/test_application_state.py`, `tests/test_applications_service.py::test_successful_transition_persists_history`, `tests/test_applications_service.py::test_failed_or_unauthorized_transition_creates_no_history`, `tests/test_applications_service.py::test_transition_route_returns_403_for_unauthorized_actor`, `tests/test_notifications.py::test_failed_status_change_has_no_history_or_notification`, `tests/test_notifications.py::test_failed_notification_insert_rolls_back_application_and_history`.

### UAT-08 — Administrator applicant export

- **Preconditions:** An administrator, a listing, and applicant records exist.
- **Steps:** Request `/api/admin/listings/{listing_id}/export` as an administrator, then repeat as an employer and graduate.
- **Expected:** An administrator can export the applicant package; other roles are refused.
- **Result:** **Not verified in this run — manual test required.** The route exists, but no dedicated export test was found in the current test suite.

### UAT-09 — Browser navigation and visual usability

- **Preconditions:** Run the app and open it in a browser.
- **Steps:** Navigate the graduate, employer, and administrator workflows using browser pages rather than API calls.
- **Expected:** Users can complete the main workflows through navigable pages.
- **Result:** **Not run / capability gap.** The repository describes a thin server-rendered authentication shell and exposes the job-board workflows as a JSON API with OpenAPI documentation at `/docs`; a complete navigable business UI is not present.

## Limitations and sign-off

- **Demo identity limitation:** Job-board API actions accept a caller-supplied `actor_id` in request bodies or query parameters. Authorization checks apply to that actor ID, but the API does not establish that it belongs to the authenticated caller. This is demo/test identity plumbing, not production-grade authentication; a production deployment should derive the actor from a verified authentication context.
- **Administrator permissions:** Administrators may review listings and have applicant viewing/export permissions. They are not allowed to transition application statuses; only the employer who owns the listing may do so.
- **Not covered:** The test run does not establish usability of a full browser UI, validate the administrator export flow, or test a deployed/production environment.
- **Tester comments:** Pending human UAT.
- **Acceptance decision:** Pending human review.
- **Tester signature / date:** Not provided.
