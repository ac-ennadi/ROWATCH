-- RoWatch Studio Plugin
-- Multi-project profiles, live session tracking, and website-matched styling.

local HttpService = game:GetService("HttpService")
local ScriptEditorService = game:GetService("ScriptEditorService")

-- Change this to your deployed RoWatch URL.
local ROWATCH_URL = "http://localhost:5000"

local COLORS = {
    bg = Color3.fromRGB(247, 249, 252),
    panel = Color3.fromRGB(255, 255, 255),
    panelAlt = Color3.fromRGB(241, 245, 249),
    text = Color3.fromRGB(24, 31, 42),
    muted = Color3.fromRGB(103, 116, 133),
    border = Color3.fromRGB(214, 222, 232),
    accent = Color3.fromRGB(11, 111, 234),
    accentHover = Color3.fromRGB(8, 91, 195),
    good = Color3.fromRGB(28, 151, 90),
    bad = Color3.fromRGB(206, 65, 52),
    white = Color3.fromRGB(255, 255, 255),
}

local toolbar = plugin:CreateToolbar("RoWatch")
local toolbarButton = toolbar:CreateButton("RoWatch", "Open RoWatch", "")
local widgetInfo = DockWidgetPluginGuiInfo.new(
    Enum.InitialDockState.Right, true, false, 390, 580, 300, 360
)
local widget = plugin:CreateDockWidgetPluginGui("RoWatchWidgetV2", widgetInfo)
widget.Title = "RoWatch"

local root = Instance.new("Frame")
root.Size = UDim2.fromScale(1, 1)
root.BackgroundColor3 = COLORS.bg
root.BorderSizePixel = 0
root.Parent = widget

local scroller = Instance.new("ScrollingFrame")
scroller.Size = UDim2.fromScale(1, 1)
scroller.BackgroundTransparency = 1
scroller.BorderSizePixel = 0
scroller.ScrollBarThickness = 4
scroller.ScrollBarImageColor3 = COLORS.accent
scroller.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroller.CanvasSize = UDim2.new()
scroller.Parent = root

local layout = Instance.new("UIListLayout")
layout.Padding = UDim.new(0, 9)
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Parent = scroller

local padding = Instance.new("UIPadding")
padding.PaddingTop = UDim.new(0, 14)
padding.PaddingBottom = UDim.new(0, 14)
padding.PaddingLeft = UDim.new(0, 14)
padding.PaddingRight = UDim.new(0, 14)
padding.Parent = scroller

local profiles = plugin:GetSetting("rw_projects") or {}
local legacyKey = plugin:GetSetting("rw_project_key") or ""
local legacyUsername = plugin:GetSetting("rw_username") or ""
if #profiles == 0 and legacyKey ~= "" and legacyUsername ~= "" then
    profiles = {{name = "Saved project", key = legacyKey, username = legacyUsername}}
    plugin:SetSetting("rw_projects", profiles)
end

local activeProfile = nil
local sessionId = nil
local sessionStart = nil
local documents = {}
local instanceQueue = {}
local lastHeartbeat = 0
local order = 0
local showProjects
local showAddProject
local showActive
local showTasks

local function saveProfiles()
    plugin:SetSetting("rw_projects", profiles)
end

local function clear()
    order = 0
    for _, child in scroller:GetChildren() do
        if child ~= layout and child ~= padding then
            child:Destroy()
        end
    end
end

local function nextOrder()
    order += 1
    return order
end

local function round(instance, radius)
    local corner = Instance.new("UICorner")
    corner.CornerRadius = UDim.new(0, radius or 5)
    corner.Parent = instance
end

local function stroke(instance, color)
    local border = Instance.new("UIStroke")
    border.Color = color or COLORS.border
    border.Thickness = 1
    border.Parent = instance
end

local function label(text, height, color, size, bold)
    local node = Instance.new("TextLabel")
    node.Size = UDim2.new(1, 0, 0, height or 22)
    node.BackgroundTransparency = 1
    node.Text = text
    node.TextColor3 = color or COLORS.text
    node.TextXAlignment = Enum.TextXAlignment.Left
    node.TextYAlignment = Enum.TextYAlignment.Center
    node.TextWrapped = true
    node.Font = bold and Enum.Font.GothamBold or Enum.Font.Gotham
    node.TextSize = size or 13
    node.LayoutOrder = nextOrder()
    node.Parent = scroller
    return node
end

local function button(text, color, textColor, height)
    local node = Instance.new("TextButton")
    node.Size = UDim2.new(1, 0, 0, height or 38)
    node.BackgroundColor3 = color or COLORS.panel
    node.TextColor3 = textColor or COLORS.text
    node.Text = text
    node.Font = Enum.Font.GothamBold
    node.TextSize = 12
    node.AutoButtonColor = true
    node.BorderSizePixel = 0
    node.LayoutOrder = nextOrder()
    node.Parent = scroller
    round(node, 5)
    stroke(node, color == COLORS.accent and COLORS.accent or COLORS.border)
    return node
end

local function input(placeholder, value, secret)
    local node = Instance.new("TextBox")
    node.Size = UDim2.new(1, 0, 0, 38)
    node.BackgroundColor3 = COLORS.panel
    node.TextColor3 = COLORS.text
    node.PlaceholderColor3 = COLORS.muted
    node.PlaceholderText = placeholder
    node.Text = value or ""
    node.ClearTextOnFocus = false
    node.TextXAlignment = Enum.TextXAlignment.Left
    node.Font = Enum.Font.Gotham
    node.TextSize = 12
    node.BorderSizePixel = 0
    node.LayoutOrder = nextOrder()
    node.Parent = scroller
    if secret then node.TextEditable = true end
    round(node, 5)
    stroke(node)
    local pad = Instance.new("UIPadding")
    pad.PaddingLeft = UDim.new(0, 10)
    pad.PaddingRight = UDim.new(0, 10)
    pad.Parent = node
    return node
end

local function header(subtitle)
    label("R  RoWatch", 30, COLORS.accent, 18, true)
    label(subtitle, 20, COLORS.muted, 11, false)
end

local function apiCall(profile, endpoint, method, body)
    if not profile or not profile.key or not profile.username then
        return nil, "Missing project credentials"
    end
    local ok, response = pcall(function()
        local requestData = {
            Url = ROWATCH_URL .. endpoint,
            Method = method or "POST",
            Headers = {
                ["Content-Type"] = "application/json",
                ["X-Project-Key"] = profile.key,
                ["X-Username"] = profile.username,
            },
        }
        if body ~= nil then
            requestData.Body = HttpService:JSONEncode(body)
        end
        return HttpService:RequestAsync(requestData)
    end)
    if not ok then return nil, tostring(response) end
    local data = nil
    if response.Body and response.Body ~= "" then
        pcall(function() data = HttpService:JSONDecode(response.Body) end)
    end
    if not response.Success then
        return nil, (data and data.error) or ("HTTP " .. tostring(response.StatusCode))
    end
    return data, nil
end

local StarterGui = game:GetService("StarterGui")
local Workspace = game:GetService("Workspace")

local function classify(instance)
    if instance:IsA("BasePart") then return "part" end
    if instance:IsA("GuiObject") or instance:IsA("LayerCollector") then
        -- UI property edits such as Position and Size are intentionally not tracked.
        if instance:IsDescendantOf(StarterGui) or instance:IsDescendantOf(Workspace) then
            return "ui"
        end
    end
    return nil
end

local function queueInstance(instance, action)
    if not sessionId then return end
    local category = classify(instance)
    if not category then return end
    local fullName = instance.Name
    pcall(function() fullName = instance:GetFullName() end)
    table.insert(instanceQueue, {
        ref = instance,
        category = category,
        action = action,
        class_name = instance.ClassName,
        instance_name = fullName,
        count = 1,
    })
end

local function flushInstanceQueue()
    if not sessionId or not activeProfile or #instanceQueue == 0 then return end
    local queued = instanceQueue
    instanceQueue = {}

    -- Roblox emits DescendantRemoving for a removed UI root and every child.
    -- Keep only the top-level removed UI object from each cascade.
    local removedUi = {}
    for _, item in ipairs(queued) do
        if item.category == "ui" and item.action == "removed" then
            removedUi[item.ref] = true
        end
    end

    local grouped = {}
    for _, item in ipairs(queued) do
        local skip = false
        if item.category == "ui" and item.action == "removed" then
            local ancestor = item.ref.Parent
            while ancestor do
                if removedUi[ancestor] then
                    skip = true
                    break
                end
                ancestor = ancestor.Parent
            end
        end
        if not skip then
            local key = item.category .. ":" .. item.action .. ":" .. item.class_name
            if grouped[key] then
                grouped[key].count += 1
            else
                grouped[key] = {
                    category = item.category,
                    action = item.action,
                    class_name = item.class_name,
                    instance_name = item.instance_name,
                    count = 1,
                }
            end
        end
    end

    local batch = {}
    for _, item in pairs(grouped) do
        table.insert(batch, item)
    end
    if #batch > 0 then
        apiCall(activeProfile, "/api/events/instance/change", "POST", {
            session_id = sessionId,
            events = batch,
        })
    end
end

game.DescendantAdded:Connect(function(instance)
    queueInstance(instance, "added")
end)

game.DescendantRemoving:Connect(function(instance)
    queueInstance(instance, "removed")
end)

task.spawn(function()
    while true do
        task.wait(1)
        if sessionId then
            flushInstanceQueue()
            if os.time() - lastHeartbeat >= 5 then
                lastHeartbeat = os.time()
                apiCall(activeProfile, "/api/events/session/heartbeat", "POST", {session_id = sessionId})
            end
        end
    end
end)

showTasks = function(profile, message)
    clear()
    header((profile.name or "Project") .. " • My tasks")
    if message then label(message, 28, COLORS.good, 11, false) end
    label("Only tasks assigned to @" .. profile.username .. " are shown.", 30, COLORS.muted, 10, false)

    local tasks, err = apiCall(profile, "/api/tasks", "GET")
    if not tasks then
        label("Could not load tasks: " .. (err or "unknown error"), 40, COLORS.bad, 11, false)
    elseif #tasks == 0 then
        label("No tasks assigned", 30, COLORS.text, 14, true)
        label("Tasks assigned from the RoWatch website will appear here.", 38, COLORS.muted, 10, false)
    else
        for _, taskItem in ipairs(tasks) do
            local prefix = taskItem.my_completed and "✓  " or "○  "
            local taskButton = button(prefix .. taskItem.title, taskItem.my_completed and COLORS.panelAlt or COLORS.panel, taskItem.my_completed and COLORS.good or COLORS.text, 42)
            taskButton.TextXAlignment = Enum.TextXAlignment.Left
            local buttonPadding = Instance.new("UIPadding")
            buttonPadding.PaddingLeft = UDim.new(0, 10)
            buttonPadding.PaddingRight = UDim.new(0, 10)
            buttonPadding.Parent = taskButton
            taskButton.MouseButton1Click:Connect(function()
                local _, toggleError = apiCall(profile, "/api/tasks/" .. taskItem.id .. "/complete", "POST", {
                    completed = not taskItem.my_completed,
                })
                if toggleError then
                    showTasks(profile, "Could not update: " .. toggleError)
                else
                    showTasks(profile, taskItem.my_completed and "Task reopened" or "Task completed")
                end
            end)
            if taskItem.description_md and taskItem.description_md ~= "" then
                local plain = taskItem.description_md:gsub("[#*_`]", ""):gsub("%s+", " ")
                if #plain > 100 then plain = plain:sub(1, 97) .. "..." end
                label(plain, 34, COLORS.muted, 10, false)
            end
            local completion = tostring(taskItem.completed_count) .. "/" .. tostring(#taskItem.assignments) .. " assignees complete"
            label(completion, 18, COLORS.muted, 9, false)
        end
    end

    local back = button(sessionId and "Back to active session" or "Back to projects", COLORS.panel, COLORS.text, 36)
    back.MouseButton1Click:Connect(function()
        if sessionId then showActive() else showProjects() end
    end)
end

showProjects = function(message)
    clear()
    header("Choose a project to start tracking")
    if message then label(message, 30, COLORS.bad, 11, false) end

    if #profiles == 0 then
        label("No saved projects", 28, COLORS.text, 14, true)
        label("Add a project once using its project key. It will stay here for future Studio sessions.", 48, COLORS.muted, 11, false)
    end

    for index, profile in ipairs(profiles) do
        local start = button("▶  " .. (profile.name or "Project"), COLORS.accent, COLORS.white, 42)
        start.MouseButton1Click:Connect(function()
            local data, err = apiCall(profile, "/api/events/session/start", "POST")
            if data and data.session_id then
                activeProfile = profile
                sessionId = data.session_id
                sessionStart = os.time()
                lastHeartbeat = 0
                instanceQueue = {}
                showActive()
            else
                showProjects("Could not start: " .. (err or "unknown error"))
            end
        end)

        local detail = label("@" .. profile.username .. "  •  saved project", 18, COLORS.muted, 10, false)
        local tasksButton = button("My assigned tasks", COLORS.panel, COLORS.accent, 32)
        tasksButton.MouseButton1Click:Connect(function() showTasks(profile) end)
        local remove = button("Remove " .. (profile.name or "project"), COLORS.panel, COLORS.bad, 30)
        remove.MouseButton1Click:Connect(function()
            table.remove(profiles, index)
            saveProfiles()
            showProjects("Project removed")
        end)
        detail.LayoutOrder = start.LayoutOrder + 1
    end

    local add = button("+  ADD PROJECT", COLORS.panel, COLORS.accent, 38)
    add.MouseButton1Click:Connect(showAddProject)
end

showAddProject = function(message)
    clear()
    header("Add a Studio project")
    if message then label(message, 34, COLORS.bad, 11, false) end
    label("RoWatch username", 18, COLORS.muted, 11, true)
    local usernameBox = input("Exact account username", legacyUsername)
    label("Project ID / key", 18, COLORS.muted, 11, true)
    local keyBox = input("Paste from Studio Integration", "")
    label("The key is validated now and saved only in Studio plugin settings.", 35, COLORS.muted, 10, false)

    local connect = button("CONNECT & SAVE", COLORS.accent, COLORS.white, 40)
    connect.MouseButton1Click:Connect(function()
        local username = usernameBox.Text:match("^%s*(.-)%s*$")
        local key = keyBox.Text:match("^%s*(.-)%s*$")
        if username == "" or key == "" then
            showAddProject("Username and project key are required")
            return
        end
        local candidate = {username = username, key = key, name = "Project"}
        local data, err = apiCall(candidate, "/api/events/ping", "GET")
        if not data or not data.ok then
            showAddProject("Connection failed: " .. (err or "check credentials"))
            return
        end
        candidate.name = data.project or "Project"
        for _, existing in ipairs(profiles) do
            if existing.key == key and existing.username == username then
                showProjects("That project is already saved")
                return
            end
        end
        table.insert(profiles, candidate)
        legacyUsername = username
        saveProfiles()
        showProjects(candidate.name .. " saved")
    end)

    local cancel = button("Back to projects", COLORS.panel, COLORS.text, 34)
    cancel.MouseButton1Click:Connect(showProjects)
end

showActive = function()
    clear()
    header(activeProfile.name or "Active project")
    label("● LIVE SESSION", 28, COLORS.good, 13, true)
    label("@" .. activeProfile.username, 18, COLORS.muted, 11, false)
    local timer = label("00h 00m 00s", 52, COLORS.text, 25, true)
    label("Tracking scripts, parts, and UI components", 24, COLORS.muted, 10, false)

    local tasksButton = button("MY ASSIGNED TASKS", COLORS.panel, COLORS.accent, 36)
    tasksButton.MouseButton1Click:Connect(function() showTasks(activeProfile) end)
    local finish = button("■  END SESSION", COLORS.panel, COLORS.bad, 40)
    finish.MouseButton1Click:Connect(function()
        flushInstanceQueue()
        apiCall(activeProfile, "/api/events/session/end", "POST", {session_id = sessionId})
        sessionId = nil
        sessionStart = nil
        activeProfile = nil
        instanceQueue = {}
        showProjects("Session saved")
    end)

    task.spawn(function()
        while sessionId and timer.Parent do
            local seconds = os.time() - (sessionStart or os.time())
            timer.Text = string.format("%02dh %02dm %02ds",
                math.floor(seconds / 3600),
                math.floor((seconds % 3600) / 60),
                seconds % 60
            )
            task.wait(1)
        end
    end)
end

pcall(function()
    ScriptEditorService.TextDocumentDidOpen:Connect(function(document)
        local scriptObject = document:GetScript()
        if not scriptObject then return end
        local ok, text = pcall(function() return document:GetText() end)
        documents[document] = {
            name = scriptObject:GetFullName(),
            startText = ok and text or "",
            lastText = ok and text or "",
        }
        if sessionId then
            apiCall(activeProfile, "/api/events/script/open", "POST", {
                session_id = sessionId,
                script = scriptObject:GetFullName(),
            })
        end
    end)

    ScriptEditorService.TextDocumentDidChange:Connect(function(document)
        local info = documents[document]
        if not info then return end
        local ok, text = pcall(function() return document:GetText() end)
        if ok then info.lastText = text end
    end)

    ScriptEditorService.TextDocumentDidClose:Connect(function(document)
        local info = documents[document]
        if not info then return end
        if sessionId then
            apiCall(activeProfile, "/api/events/script/close", "POST", {
                session_id = sessionId,
                script = info.name,
                chars_added = math.max(#info.lastText - #info.startText, 0),
                chars_removed = math.max(#info.startText - #info.lastText, 0),
            })
        end
        documents[document] = nil
    end)
end)

toolbarButton.Click:Connect(function()
    widget.Enabled = not widget.Enabled
    if widget.Enabled then
        if sessionId then showActive() else showProjects() end
    end
end)

plugin.Unloading:Connect(function()
    if sessionId and activeProfile then
        flushInstanceQueue()
        apiCall(activeProfile, "/api/events/session/end", "POST", {session_id = sessionId})
    end
end)

showProjects()
