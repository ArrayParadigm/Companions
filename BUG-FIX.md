## 0.1.17.3-001
# BUG
    Signed-out users could still see Dashboard category content after the Home/Dashboard merge.
# Cause
    The logged-out state hid navigation buttons but did not explicitly hide Dashboard content cards inside the active Dashboard section.
# Solution
    Dashboard content is now separated from the auth landing controls. Logged-out users see only login/register controls, while signed-in users see the Session panel and Dashboard content.

## 0.1.17.2-001
# BUG
    After the Home/Dashboard merge, the app did not clearly show whether the user was signed in or which categories were enabled.
# Cause
    The Dashboard auth panel was hidden after login, leaving only the compact header label and making it hard to distinguish login state from category gating.
# Solution
    Dashboard now keeps an explicit Session panel visible after login with the signed-in profile, role, companion access, and per-category access state.

## 0.1.17.1-001
# BUG
    The live site showed a browser username/password popup before the app loaded.
# Cause
    The Apache subdomain setup enabled Basic Auth by default, creating a site-gateway login in front of the app.
# Solution
    The Linux setup now defaults `REQUIRE_BASIC_AUTH` to `0`, keeps Basic Auth only as an explicit override, and the docs include live vhost cleanup commands for removing the existing Basic Auth directives without touching other Apache sites.

## 0.1.17.1-002
# BUG
    Nearly all categories could be missing after login on live or older profile data.
# Cause
    Category visibility trusted stored profile access metadata, so stale or incomplete `Array` access toggles could hide owner categories even though `Array` should have full access.
# Solution
    `Array` now resolves to full category access server-side regardless of stored legacy toggles, and public profile metadata mirrors that owner full-access behavior for the UI.

## 0.1.17.0-001
# BUG
    When signing in for the first time, not all relevant categories loaded until a manual refresh.
# Cause
    The signed-out state hid most navigation buttons, and the authenticated state only refreshed access-gated buttons. Non-gated tabs such as Dashboard, Calendar, and Profile Settings could stay hidden after first login.
# Solution
    Authenticated access rendering now restores unrestricted navigation buttons before applying companion/admin/category gates, so first-login category visibility is rebuilt immediately.
