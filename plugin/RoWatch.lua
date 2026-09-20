-- RoWatch Studio Plugin
-- Multi-project profiles, live session tracking, and website-matched styling.

local HttpService = game:GetService("HttpService")
local ScriptEditorService = game:GetService("ScriptEditorService")
local TweenService = game:GetService("TweenService")
local StudioService = game:GetService("StudioService")
local Players = game:GetService("Players")

-- Change this to your deployed RoWatch URL.
local ROWATCH_URL = "http://localhost:5000"

local THEMES = {
    light = {
        bg = Color3.fromRGB(244, 247, 251),
        panel = Color3.fromRGB(255, 255, 255),
        panelAlt = Color3.fromRGB(237, 243, 250),
        text = Color3.fromRGB(19, 28, 42),
        muted = Color3.fromRGB(96, 111, 132),
        border = Color3.fromRGB(211, 221, 234),
        accent = Color3.fromRGB(37, 99, 235),
        accentHover = Color3.fromRGB(29, 78, 216),
        accentSoft = Color3.fromRGB(229, 238, 255),
        good = Color3.fromRGB(22, 163, 100),
        goodSoft = Color3.fromRGB(226, 247, 237),
        bad = Color3.fromRGB(220, 61, 61),
        badSoft = Color3.fromRGB(254, 235, 235),
        white = Color3.fromRGB(255, 255, 255),
    },
    dark = {
        bg = Color3.fromRGB(15, 20, 29),
        panel = Color3.fromRGB(24, 31, 43),
        panelAlt = Color3.fromRGB(31, 41, 56),
        text = Color3.fromRGB(238, 243, 250),
        muted = Color3.fromRGB(151, 164, 184),
        border = Color3.fromRGB(52, 64, 82),
        accent = Color3.fromRGB(79, 140, 255),
        accentHover = Color3.fromRGB(105, 159, 255),
        accentSoft = Color3.fromRGB(31, 54, 91),
        good = Color3.fromRGB(62, 207, 142),
        goodSoft = Color3.fromRGB(24, 66, 54),
        bad = Color3.fromRGB(255, 112, 112),
        badSoft = Color3.fromRGB(76, 38, 43),
        white = Color3.fromRGB(255, 255, 255),
    },
}

local savedTheme = plugin:GetSetting("rw_theme")
local themeName = savedTheme == "light" and "light" or "dark"
local COLORS = THEMES[themeName]


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
local accountApiKey = plugin:GetSetting("rw_account_api_key") or ""
local pluginUsername = plugin:GetSetting("rw_account_username") or ""


local activeProfile = nil
local sessionId = nil
local sessionStart = nil
local documents = {}
local instanceQueue = {}
local lastHeartbeat = 0
local order = 0
local showProjects
local showActive
local showTasks
local showAuth
local redraw

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
    return border
end

local function addPadding(instance, horizontal, vertical)
    local pad = Instance.new("UIPadding")
    pad.PaddingLeft = UDim.new(0, horizontal or 12)
    pad.PaddingRight = UDim.new(0, horizontal or 12)
    pad.PaddingTop = UDim.new(0, vertical or 0)
    pad.PaddingBottom = UDim.new(0, vertical or 0)
    pad.Parent = instance
    return pad
end

local function label(text, height, color, size, bold, parent)
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
    node.Parent = parent or scroller
    return node
end

local function card(parent, paddingSize, gap)
    local node = Instance.new("Frame")
    node.Size = UDim2.new(1, 0, 0, 0)
    node.AutomaticSize = Enum.AutomaticSize.Y
    node.BackgroundColor3 = COLORS.panel
    node.BorderSizePixel = 0
    node.LayoutOrder = nextOrder()
    node.Parent = parent or scroller
    round(node, 9)
    stroke(node)
    addPadding(node, paddingSize or 13, paddingSize or 13)
    local cardLayout = Instance.new("UIListLayout")
    cardLayout.Padding = UDim.new(0, gap or 8)
    cardLayout.SortOrder = Enum.SortOrder.LayoutOrder
    cardLayout.Parent = node
    return node
end

local function button(text, color, textColor, height, parent)
    local node = Instance.new("TextButton")
    node.Size = UDim2.new(1, 0, 0, height or 38)
    node.BackgroundColor3 = color or COLORS.panel
    node.TextColor3 = textColor or COLORS.text
    node.Text = text
    node.Font = Enum.Font.GothamBold
    node.TextSize = 12
    node.AutoButtonColor = false
    node.BorderSizePixel = 0
    node.LayoutOrder = nextOrder()
    node.Parent = parent or scroller
    round(node, 7)
    stroke(node, color == COLORS.accent and COLORS.accent or COLORS.border)

    local scale = Instance.new("UIScale")
    scale.Parent = node
    node:SetAttribute("BaseColor", node.BackgroundColor3)
    node.MouseEnter:Connect(function()
        local baseColor = node:GetAttribute("BaseColor")
        local target = baseColor == COLORS.accent and COLORS.accentHover or COLORS.panelAlt
        TweenService:Create(node, TweenInfo.new(0.14), {BackgroundColor3 = target}):Play()
    end)
    node.MouseLeave:Connect(function()
        TweenService:Create(node, TweenInfo.new(0.14), {BackgroundColor3 = node:GetAttribute("BaseColor")}):Play()
        TweenService:Create(scale, TweenInfo.new(0.1), {Scale = 1}):Play()
    end)
    node.MouseButton1Down:Connect(function()
        TweenService:Create(scale, TweenInfo.new(0.08), {Scale = 0.975}):Play()
    end)
    node.MouseButton1Up:Connect(function()
        TweenService:Create(scale, TweenInfo.new(0.12, Enum.EasingStyle.Back), {Scale = 1}):Play()
    end)
    return node
end

local function input(placeholder, value, secret, parent)
    local node = Instance.new("TextBox")
    node.Size = UDim2.new(1, 0, 0, 40)
    node.BackgroundColor3 = COLORS.panelAlt
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
    node.Parent = parent or scroller
    if secret then node.TextEditable = true end
    round(node, 7)
    local inputStroke = stroke(node)
    addPadding(node, 11, 0)
    node.Focused:Connect(function()
        TweenService:Create(inputStroke, TweenInfo.new(0.12), {Color = COLORS.accent, Thickness = 2}):Play()
    end)
    node.FocusLost:Connect(function()
        TweenService:Create(inputStroke, TweenInfo.new(0.12), {Color = COLORS.border, Thickness = 1}):Play()
    end)
    return node
end

local function actionRow(parent, height)
    local row = Instance.new("Frame")
    row.Size = UDim2.new(1, 0, 0, height or 34)
    row.BackgroundTransparency = 1
    row.LayoutOrder = nextOrder()
    row.Parent = parent
    local rowLayout = Instance.new("UIListLayout")
    rowLayout.FillDirection = Enum.FillDirection.Horizontal
    rowLayout.Padding = UDim.new(0, 7)
    rowLayout.SortOrder = Enum.SortOrder.LayoutOrder
    rowLayout.Parent = row
    return row
end

local function banner(text, kind)
    local colors = kind == "error" and {COLORS.badSoft, COLORS.bad} or {COLORS.goodSoft, COLORS.good}
    local node = label(text, 38, colors[2], 11, true)
    node.BackgroundColor3 = colors[1]
    node.BackgroundTransparency = 0
    round(node, 7)
    addPadding(node, 11, 0)
    return node
end

local function header(subtitle)
    root.BackgroundColor3 = COLORS.bg
    scroller.ScrollBarImageColor3 = COLORS.accent

    local shell = Instance.new("Frame")
    shell.Size = UDim2.new(1, 0, 0, 68)
    shell.BackgroundColor3 = COLORS.panel
    shell.BorderSizePixel = 0
    shell.LayoutOrder = nextOrder()
    shell.Parent = scroller
    round(shell, 10)
    stroke(shell)

    local mark = Instance.new("TextLabel")
    mark.Size = UDim2.fromOffset(36, 36)
    mark.Position = UDim2.fromOffset(12, 10)
    mark.BackgroundColor3 = COLORS.accent
    mark.Text = "R"
    mark.TextColor3 = COLORS.white
    mark.Font = Enum.Font.GothamBold
    mark.TextSize = 18
    mark.BorderSizePixel = 0
    mark.Parent = shell
    round(mark, 9)

    local brand = Instance.new("TextLabel")
    brand.Size = UDim2.new(1, -104, 0, 24)
    brand.Position = UDim2.fromOffset(58, 8)
    brand.BackgroundTransparency = 1
    brand.Text = "RoWatch"
    brand.TextColor3 = COLORS.text
    brand.TextXAlignment = Enum.TextXAlignment.Left
    brand.Font = Enum.Font.GothamBold
    brand.TextSize = 16
    brand.Parent = shell

    local sub = Instance.new("TextLabel")
    sub.Size = UDim2.new(1, -104, 0, 20)
    sub.Position = UDim2.fromOffset(58, 33)
    sub.BackgroundTransparency = 1
    sub.Text = subtitle
    sub.TextColor3 = COLORS.muted
    sub.TextXAlignment = Enum.TextXAlignment.Left
    sub.TextTruncate = Enum.TextTruncate.AtEnd
    sub.Font = Enum.Font.Gotham
    sub.TextSize = 10
    sub.Parent = shell

    local themeToggle = Instance.new("TextButton")
    themeToggle.Size = UDim2.fromOffset(36, 36)
    themeToggle.AnchorPoint = Vector2.new(1, 0)
    themeToggle.Position = UDim2.new(1, -12, 0, 10)
    themeToggle.BackgroundColor3 = COLORS.panelAlt
    themeToggle.Text = themeName == "dark" and "SUN" or "MOON"
    themeToggle.TextColor3 = COLORS.accent
    themeToggle.Font = Enum.Font.GothamBold
    themeToggle.TextSize = 8
    themeToggle.AutoButtonColor = false
    themeToggle.BorderSizePixel = 0
    themeToggle.Parent = shell
    round(themeToggle, 8)
    themeToggle.MouseButton1Click:Connect(function()
        themeName = themeName == "dark" and "light" or "dark"
        COLORS = THEMES[themeName]
        plugin:SetSetting("rw_theme", themeName)
        if redraw then redraw() end
    end)
end


local function requestApi(endpoint, method, body, headers)
    local ok, response = pcall(function()
        local requestData = {
            Url = ROWATCH_URL .. endpoint,
            Method = method or "POST",
            Headers = headers or {["Content-Type"] = "application/json"},
        }
        requestData.Headers["Content-Type"] = "application/json"
        if body ~= nil then requestData.Body = HttpService:JSONEncode(body) end
        return HttpService:RequestAsync(requestData)
    end)
    if not ok then return nil, tostring(response), 0 end
    local data = nil
    if response.Body and response.Body ~= "" then
        pcall(function() data = HttpService:JSONDecode(response.Body) end)
    end
    if not response.Success then
        return nil, (data and data.error) or ("HTTP " .. tostring(response.StatusCode)), response.StatusCode
    end
    return data, nil, response.StatusCode
end

local function saveAccountConnection(rawKey, data)
    accountApiKey = rawKey
    pluginUsername = data.username or ""
    profiles = data.projects or {}
    plugin:SetSetting("rw_account_api_key", accountApiKey)
    plugin:SetSetting("rw_account_username", pluginUsername)
    plugin:SetSetting("rw_projects", profiles)
end

local function fetchAccountProjects(rawKey)
    return requestApi("/api/plugin/projects", "GET", nil, {
        ["X-API-Key"] = rawKey,
    })
end

local function apiCall(profile, endpoint, method, body)
    if not profile or not profile.id then
        return nil, "Missing selected project"
    end
    if accountApiKey == "" then
        return nil, "Account API key required"
    end
    local data, err, status = requestApi(endpoint, method, body, {
        ["X-API-Key"] = accountApiKey,
        ["X-Project-ID"] = profile.id,
    })
    if status == 401 then
        accountApiKey = ""
        plugin:SetSetting("rw_account_api_key", "")
        task.defer(function()
            if showAuth then showAuth("API key is invalid. Copy the current key from Account.") end
        end)
    end
    return data, err
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

showAuth = function(message)
    redraw = function() showAuth() end
    clear()
    header("Connect account")
    if message then banner(message, "error") end

    local keyCard = card()
    label("Account API key", 27, COLORS.text, 15, true, keyCard)
    label("Open Account on the RoWatch website, copy your API key, and paste it here. The key identifies your account securely.", 54, COLORS.muted, 10, false, keyCard)
    local keyBox = input("Paste 64-character API key", "", true, keyCard)
    local connectButton = button("Connect and fetch projects", COLORS.accent, COLORS.white, 42, keyCard)
    connectButton.MouseButton1Click:Connect(function()
        local rawKey = keyBox.Text:match("^%s*(.-)%s*$")
        if rawKey == "" then
            showAuth("Enter your account API key")
            return
        end
        connectButton.Text = "Loading memberships..."
        local data, err = fetchAccountProjects(rawKey)
        if not data then
            showAuth(err or "Invalid API key")
            return
        end
        saveAccountConnection(rawKey, data)
        showProjects("Connected as @" .. pluginUsername)
    end)
    label("Regenerating the key on the website signs this Studio plugin out immediately.", 34, COLORS.muted, 9, false, keyCard)
end


showTasks = function(profile, message)
    redraw = function() showTasks(profile) end
    clear()
    header((profile.name or "Project") .. " / My tasks")
    if message then banner(message, message:find("Could not") and "error" or "success") end

    local intro = card()
    label("Assigned to you", 24, COLORS.text, 14, true, intro)
    label("Only tasks assigned to @" .. pluginUsername .. " appear here. Select a task to change your completion status.", 38, COLORS.muted, 10, false, intro)

    local tasks, err = apiCall(profile, "/api/tasks", "GET")
    if not tasks then
        banner("Could not load tasks: " .. (err or "unknown error"), "error")
    elseif #tasks == 0 then
        local empty = card()
        label("You are all caught up", 28, COLORS.text, 14, true, empty)
        label("New tasks assigned from the RoWatch website will appear here.", 38, COLORS.muted, 10, false, empty)
    else
        label(tostring(#tasks) .. " TASK" .. (#tasks == 1 and "" or "S"), 18, COLORS.muted, 9, true)
        for _, taskItem in ipairs(tasks) do
            local taskCard = card()
            local taskButton = button("", taskItem.my_completed and COLORS.goodSoft or COLORS.panelAlt, taskItem.my_completed and COLORS.good or COLORS.text, 42, taskCard)
            taskButton.TextXAlignment = Enum.TextXAlignment.Left
            addPadding(taskButton, 11, 0)

            local function updateTaskVisual()
                taskButton.Text = (taskItem.my_completed and "[x]  " or "[ ]  ") .. taskItem.title
                taskButton.TextColor3 = taskItem.my_completed and COLORS.good or COLORS.text
                local base = taskItem.my_completed and COLORS.goodSoft or COLORS.panelAlt
                taskButton.BackgroundColor3 = base
                taskButton:SetAttribute("BaseColor", base)
            end
            updateTaskVisual()

            if taskItem.description_md and taskItem.description_md ~= "" then
                local plain = taskItem.description_md:gsub("[#*_]", ""):gsub("%s+", " ")
                if #plain > 130 then plain = plain:sub(1, 127) .. "..." end
                label(plain, 38, COLORS.muted, 10, false, taskCard)
            end
            local completionLabel = label("", 18, COLORS.muted, 9, false, taskCard)
            local function updateCompletion()
                completionLabel.Text = tostring(taskItem.completed_count) .. "/" .. tostring(#taskItem.assignments) .. " assignees complete"
            end
            updateCompletion()

            taskButton.MouseButton1Click:Connect(function()
                local nextCompleted = not taskItem.my_completed
                local _, toggleError = apiCall(profile, "/api/tasks/" .. taskItem.id .. "/complete", "POST", {
                    completed = nextCompleted,
                })
                if toggleError then
                    showTasks(profile, "Could not update: " .. toggleError)
                    return
                end
                taskItem.my_completed = nextCompleted
                taskItem.completed_count += nextCompleted and 1 or -1
                updateTaskVisual()
                updateCompletion()
            end)
        end
    end

    local back = button(sessionId and "Back to live session" or "Back to projects", COLORS.panel, COLORS.text, 38)
    back.MouseButton1Click:Connect(function()
        if sessionId then showActive() else showProjects() end
    end)
end

showProjects = function(message, isError)
    redraw = function() showProjects() end
    clear()
    header("Projects")
    if message then banner(message, isError and "error" or "success") end

    local intro = card()
    label("Start tracking", 25, COLORS.text, 15, true, intro)
    label("Choose a project fetched from your RoWatch account.", 26, COLORS.muted, 10, false, intro)

    if #profiles == 0 then
        local empty = card()
        label("No project memberships", 28, COLORS.text, 14, true, empty)
        label("Join or create a project on the website, then refresh memberships here.", 42, COLORS.muted, 10, false, empty)
    end

    for index, profile in ipairs(profiles) do
        local profileCard = card()
        label(profile.name or "Project", 25, COLORS.text, 14, true, profileCard)
        label("@" .. pluginUsername .. "  /  Ready to connect", 18, COLORS.muted, 10, false, profileCard)

        local startButton = button("Start session", COLORS.accent, COLORS.white, 40, profileCard)
        startButton.MouseButton1Click:Connect(function()
            startButton.Text = "Connecting..."
            local data, err = apiCall(profile, "/api/events/session/start", "POST")
            if data and data.session_id then
                activeProfile = profile
                sessionId = data.session_id
                sessionStart = os.time()
                lastHeartbeat = 0
                instanceQueue = {}
                showActive()
            else
                showProjects("Could not start: " .. (err or "unknown error"), true)
            end
        end)

        local tasksButton = button("My assigned tasks", COLORS.panelAlt, COLORS.accent, 34, profileCard)
        tasksButton.MouseButton1Click:Connect(function() showTasks(profile) end)
    end

    local refresh = button("Refresh project memberships", COLORS.panel, COLORS.accent, 40)
    refresh.MouseButton1Click:Connect(function()
        local data, err = fetchAccountProjects(accountApiKey)
        if not data then
            showAuth(err or "Could not refresh projects")
            return
        end
        saveAccountConnection(accountApiKey, data)
        showProjects("Projects refreshed")
    end)
    local signOut = button("Disconnect account", COLORS.panel, COLORS.bad, 36)
    signOut.MouseButton1Click:Connect(function()
        accountApiKey = ""
        profiles = {}
        plugin:SetSetting("rw_account_api_key", "")
        plugin:SetSetting("rw_projects", profiles)
        showAuth()
    end)
    label("Server  " .. ROWATCH_URL, 18, COLORS.muted, 9, false)
end



showActive = function()
    redraw = function() showActive() end
    clear()
    header(activeProfile.name or "Live session")

    local liveCard = card(nil, 16, 8)
    local live = label("LIVE  /  TRACKING", 22, COLORS.good, 11, true, liveCard)
    live.BackgroundColor3 = COLORS.goodSoft
    live.BackgroundTransparency = 0
    round(live, 6)
    addPadding(live, 9, 0)
    label(activeProfile.name or "Active project", 28, COLORS.text, 16, true, liveCard)
    label("@" .. pluginUsername, 18, COLORS.muted, 10, false, liveCard)
    local timer = label("00h 00m 00s", 56, COLORS.text, 27, true, liveCard)
    timer.TextXAlignment = Enum.TextXAlignment.Center
    label("Scripts, parts, and UI additions/removals are being tracked.", 34, COLORS.muted, 10, false, liveCard)

    local tasksButton = button("View my assigned tasks", COLORS.panel, COLORS.accent, 38)
    tasksButton.MouseButton1Click:Connect(function() showTasks(activeProfile) end)
    local finish = button("End and save session", COLORS.badSoft, COLORS.bad, 42)
    finish.MouseButton1Click:Connect(function()
        finish.Text = "Saving session..."
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
            timer.Text = string.format("%02dh  %02dm  %02ds",
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
        if accountApiKey == "" then showAuth()
        elseif sessionId then showActive()
        else showProjects() end
    end
end)

plugin.Unloading:Connect(function()
    if sessionId and activeProfile then
        flushInstanceQueue()
        apiCall(activeProfile, "/api/events/session/end", "POST", {session_id = sessionId})
    end
end)

if accountApiKey == "" then showAuth() else showProjects() end
