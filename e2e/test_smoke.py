"""
File:   test_smoke.py
Brief:  Playwright UI/UX smoke tests exercising the app under /mech subpath.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Nine tests covering login, consent checkbox state, navigation, user CRUD,
role-based visibility, session restore, and logout. Russian UI text in selectors
is expected.

Expected failures against current code:
- test_admin_navigation_no_console_errors: monitor catches 404s from ChatView
  (empty vehicle-id) and FleetView (absolute /api/vehicles URL).
- test_admin_users_crud: AdminView password/api-key inputs lack autocomplete.
"""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

NEW_FLAGGED_PASSWORD: str = "new-flagged-pass-99"

# ---------------------------------------------------------------------------
# Helper: login
# ---------------------------------------------------------------------------


def login(
    page: Page, stand: Any, username: str, password: str
) -> None:
    """Navigate to base_url, fill the login form, click Войти, wait for topbar."""
    page.goto(stand.base_url)
    page.fill("#login-user", username)
    page.fill("#login-pass", password)
    page.locator("#login-consent").check()
    page.get_by_role("button", name="Войти").click()
    # Wait for the authenticated topbar to appear.
    page.wait_for_selector('button:has-text("Гараж")')


# ---------------------------------------------------------------------------
# Test 1: Login page renders clean
# ---------------------------------------------------------------------------


def test_login_page_renders_clean(page: Page, stand: Any) -> None:
    """Assert the login page renders with expected elements and attributes."""
    page.goto(stand.base_url)

    # H1 should show the app title in Russian.
    page.wait_for_selector("h1", state="visible")
    h1 = page.locator("h1")
    assert h1.is_visible()
    assert "Цифровой механик" in h1.inner_text()

    # Login form inputs must be present.
    page.wait_for_selector("#login-user", state="visible")
    page.wait_for_selector("#login-pass", state="visible")

    # Every password input on the page should have a non-empty autocomplete attr.
    pw_inputs = page.locator("input[type=password]")
    count = pw_inputs.count()
    for i in range(count):
        autocomplete = pw_inputs.nth(i).get_attribute("autocomplete")
        assert autocomplete, (
            f"Password input at index {i} has empty or missing autocomplete attribute"
        )


# ---------------------------------------------------------------------------
# Test 2: Login rejects wrong password
# ---------------------------------------------------------------------------


def test_login_rejects_wrong_password(page: Page, stand: Any) -> None:
    """Wrong password -> .error-strip visible; login form still present."""
    page.goto(stand.base_url)
    page.fill("#login-user", "admin")
    page.fill("#login-pass", "totally-wrong-pass")
    page.locator("#login-consent").check()
    page.get_by_role("button", name="Войти").click()

    # The auth/login 401 is allowlisted by the error monitor.
    page.wait_for_selector(".error-strip", state="visible")

    # Login form must still be visible (it never hides on failure).
    page.wait_for_selector("#login-user", state="visible")
    page.wait_for_selector("#login-pass", state="visible")


# ---------------------------------------------------------------------------
# Test 3: Consent checkbox controls submit button disabled state
# ---------------------------------------------------------------------------


def test_login_consent_checkbox_disabled(page: Page, stand: Any) -> None:
    """Assert submit button is disabled before consent checked and enabled after."""
    page.goto(stand.base_url)

    page.wait_for_selector("#login-user", state="visible")
    page.fill("#login-user", "admin")
    page.fill("#login-pass", "admin")

    # Submit button should be disabled before checkbox is checked.
    submit_btn = page.get_by_role("button", name="Войти")
    assert submit_btn.is_disabled(), "Submit button must be disabled without consent"

    # Check the consent checkbox.
    page.locator("#login-consent").check()

    # After checking, submit button should become enabled.
    assert not submit_btn.is_disabled(), (
        "Submit button must be enabled after consent is checked"
    )


# ---------------------------------------------------------------------------
# Test 4: Admin navigation -- no console errors (may fail due to known bugs)
# ---------------------------------------------------------------------------


def test_admin_navigation_no_console_errors(
    page: Page, stand: Any
) -> None:
    """Login as admin and traverse all nav tabs; monitor catches 404s."""
    login(page, stand, stand.admin_user, stand.admin_password)

    # --- Garage tab ---
    page.wait_for_selector('button:has-text("Гараж")', state="visible")
    garage_cards = page.locator(".vehicle-card")
    assert garage_cards.count() >= 1, "Expected at least one vehicle card"
    assert "Г-101" in page.content(), 'Expected garage number "Г-101" on the page'

    # --- Chat tab ---
    # Select a vehicle first so ChatView has a vehicleId (quick-chips require it).
    page.locator(".vehicle-card").first.click()
    page.wait_for_selector('button:has-text("Чат")', state="visible")
    page.get_by_role("button", name="Чат").click()
    # ChatView renders quick-chips when empty chat with a vehicle selected.
    first_chip = page.locator(".quick-chip").first
    assert first_chip.is_visible(), "Expected at least one quick-chip on Chat page"
    chip_text = first_chip.inner_text()
    assert (
        "Получить диагностику" in chip_text
    ), f'Expected "Получить диагностику" in chip text, got: {chip_text}'

    # --- Fleet tab ---
    page.get_by_role("button", name="Парк").click()
    page.wait_for_selector(".group-card", state="visible")
    fleet_details = page.locator("details.fleet-details")
    assert fleet_details.count() >= 1, "Expected fleet-details element"

    # Click the fleet-summary to expand the table.
    fleet_summary = page.locator(".fleet-summary")
    if not fleet_details.locator("summary").evaluate(
        "(el) => el.parentElement.open"
    ):
        fleet_summary.click()
        page.wait_for_selector(".fleet-table tr", state="visible")

    # At least one data row in the table.
    fleet_rows = page.locator(".fleet-table tr")
    assert fleet_rows.count() > 0, "Expected at least one fleet table row"

    # --- Admin tab ---
    page.get_by_role("button", name="Админ").click()
    page.get_by_role("button", name="Дашборд").click()
    page.wait_for_selector('h3:has-text("Дашборд использования")', state="visible")

    # --- Back to Garage ---
    page.get_by_role("button", name="Гараж").click()
    garage_cards = page.locator(".vehicle-card")
    assert garage_cards.count() >= 1, "Expected vehicle cards on Garage tab"


# ---------------------------------------------------------------------------
# Test 5: Admin users CRUD (may fail -- missing autocomplete attrs)
# ---------------------------------------------------------------------------


def test_admin_users_crud(page: Page, stand: Any) -> None:
    """Create user via admin UI; delete user with confirm dialog."""
    login(page, stand, stand.admin_user, stand.admin_password)

    # Navigate to Admin -> Users tab.
    page.get_by_role("button", name="Админ").click()
    page.get_by_role("button", name="Пользователи").click()

    # Assert every password input has a non-empty autocomplete attribute.
    pw_inputs = page.locator("input[type=password]")
    count = pw_inputs.count()
    for i in range(count):
        autocomplete = pw_inputs.nth(i).get_attribute("autocomplete")
        assert autocomplete, (
            f"Password input at index {i} has empty or missing autocomplete attribute"
        )

    # Open the add-user accordion.
    page.locator("details summary:has-text('Добавить пользователя')").click()

    # Fill in the new user form.
    page.get_by_placeholder("Имя пользователя").fill("e2e-ui-user")
    page.get_by_placeholder("Пароль (мин. 8)").fill("e2e-ui-pass-123")
    page.get_by_role("button", name="Создать").click()

    # Assert the new user appears in the table.
    page.wait_for_selector('td:has-text("e2e-ui-user")', state="visible")

    # Click the "Удалить" button on that row and accept the confirm dialog.
    delete_btn = page.locator(
        'td:has-text("e2e-ui-user")'
    ).locator("..").locator(".actions-cell").get_by_role("button", name="Удалить")
    delete_btn.click()

    # The ConfirmDialog renders inside AppModal which Teleports to body.
    # Scope the accept button to the modal overlay to avoid strict-mode violations.
    modal = page.locator(".modal-overlay")
    assert modal.is_visible(), "Expected confirm dialog modal to be visible"
    modal.get_by_role("button", name="Удалить").click()

    # Assert the row disappears.
    page.wait_for_selector('td:has-text("e2e-ui-user")', state="hidden")


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test 6: Regular user hides admin tab
# ---------------------------------------------------------------------------


def test_regular_user_hides_admin(page: Page, stand: Any) -> None:
    """Non-admin user should not see the Админ button."""
    login(page, stand, stand.user_user, stand.user_password)

    admin_btn = page.get_by_role("button", name="Админ")
    assert admin_btn.count() == 0, "Expected no Админ button for regular user"

    garage_cards = page.locator(".vehicle-card")
    assert (
        garage_cards.count() >= 1
    ), "Expected at least one vehicle card for regular user"


def test_reload_restores_session(page: Page, stand: Any) -> None:
    """After page.reload(), the authenticated topbar should still be visible."""
    login(page, stand, stand.admin_user, stand.admin_password)

    page.reload()

    page.wait_for_selector('button:has-text("Гараж")', state="visible")


def test_logout_returns_to_login(page: Page, stand: Any) -> None:
    """Clicking Выйти should return the user to the login form."""
    login(page, stand, stand.admin_user, stand.admin_password)

    page.get_by_role("button", name="Выйти").click()

    page.wait_for_selector("#login-user", state="visible")
    page.wait_for_selector("#login-pass", state="visible")


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Test 9: Forced password-change modal
# ---------------------------------------------------------------------------


def test_forced_password_change_modal(
    page: Page, stand: Any
) -> None:
    """Login with must_change_password=1 → modal appears, change password, verify."""
    # 1. Login as the flagged user — topbar appears (helper waits for it).
    login(page, stand, stand.flagged_user, stand.flagged_password)

    # 2. Mandatory modal must be visible and have no dismiss affordance.
    page.wait_for_selector(".modal-overlay", state="visible")
    assert page.locator(".modal-overlay .modal-close").count() == 0, (
        "Modal must have no close button"
    )

    # 3. Fill in old password + new password fields.
    page.fill("#pwd-old", stand.flagged_password)
    page.fill("#pwd-new", NEW_FLAGGED_PASSWORD)
    page.fill("#pwd-confirm", NEW_FLAGGED_PASSWORD)

    # 4. Click the save button scoped to the modal.
    page.locator(".modal-overlay").get_by_role(
        "button", name="Сохранить пароль"
    ).click()

    # 5. Mandatory modal must disappear after successful change.
    page.wait_for_selector(".modal-overlay", state="hidden")

    # 6. Garage data must load (vehicle cards appear).
    page.wait_for_selector(".vehicle-card", state="visible")

    # 7. Log out — click Выйти in the topbar.
    page.get_by_role("button", name="Выйти").click()
    page.wait_for_selector("#login-user", state="visible")

    # 8. Old password must now be rejected (401 → .error-strip).
    page.fill("#login-user", stand.flagged_user)
    page.fill("#login-pass", stand.flagged_password)
    page.locator("#login-consent").check()
    page.get_by_role("button", name="Войти").click()
    page.wait_for_selector(".error-strip", state="visible")

    # Refresh to get a fresh LoginView component (loading state resets).
    page.goto(stand.base_url)
    page.wait_for_selector("#login-user", state="visible")

    # 9. New password must work: fill form, check consent, click Войти, wait for topbar.
    page.fill("#login-user", stand.flagged_user)
    page.fill("#login-pass", NEW_FLAGGED_PASSWORD)
    page.locator("#login-consent").check()
    page.get_by_role("button", name="Войти").click(force=True)
    page.wait_for_selector('button:has-text("Гараж")', state="visible")
