from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1] / "plugin" / "RoWatch.lua"


def source():
    return PLUGIN.read_text(encoding="utf-8")


def test_plugin_has_persisted_light_and_dark_themes():
    lua = source()
    assert "local THEMES = {" in lua
    assert "light = {" in lua
    assert "dark = {" in lua
    assert 'plugin:GetSetting("rw_theme")' in lua
    assert 'plugin:SetSetting("rw_theme", themeName)' in lua
    assert 'themeName = themeName == "dark" and "light" or "dark"' in lua


def test_plugin_uses_cards_focus_states_and_button_motion():
    lua = source()
    assert 'local function card(' in lua
    assert 'local function banner(' in lua
    assert 'local function actionRow(' in lua
    assert 'TweenService:Create(node' in lua
    assert 'node.MouseButton1Down:Connect' in lua
    assert 'node.Focused:Connect' in lua
    assert 'return border' in lua


def test_task_completion_updates_in_place():
    lua = source()
    success_update = '''taskItem.my_completed = nextCompleted
                taskItem.completed_count += nextCompleted and 1 or -1
                updateTaskVisual()
                updateCompletion()'''
    assert success_update in lua
    assert 'taskButton:SetAttribute("BaseColor", base)' in lua


def test_plugin_core_tracking_and_multi_project_behavior_remain_connected():
    lua = source()
    for endpoint in (
        "/api/events/session/start",
        "/api/events/session/heartbeat",
        "/api/events/session/end",
        "/api/events/script/open",
        "/api/events/script/close",
        "/api/events/instance/change",
        "/api/tasks",
    ):
        assert endpoint in lua
    assert 'plugin:GetSetting("rw_projects")' in lua
    assert 'plugin:SetSetting("rw_projects", profiles)' in lua
    assert 'plugin:GetSetting("rw_account_api_key")' in lua
    assert 'plugin:SetSetting("rw_account_api_key", accountApiKey)' in lua
    assert '["X-API-Key"] = accountApiKey' in lua
    assert '["X-Project-ID"] = profile.id' in lua
    assert '"/api/plugin/projects"' in lua
    assert 'X-Username' not in lua
    assert 'X-Project-Key' not in lua
    assert "instance:IsDescendantOf(StarterGui) or instance:IsDescendantOf(Workspace)" in lua
