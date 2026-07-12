## 0.1.17.0-001
# BUG
    When signing in for the first time, not all relevant categories loaded until a manual refresh.
# Cause
    The signed-out state hid most navigation buttons, and the authenticated state only refreshed access-gated buttons. Non-gated tabs such as Dashboard, Calendar, and Profile Settings could stay hidden after first login.
# Solution
    Authenticated access rendering now restores unrestricted navigation buttons before applying companion/admin/category gates, so first-login category visibility is rebuilt immediately.
