local HttpService = game:GetService("HttpService")
local ScriptEditorService = game:GetService("ScriptEditorService")
local TweenService = game:GetService("TweenService")
local StudioService = game:GetService("StudioService")
local Players = game:GetService("Players")

local ROWATCH_URL = "https://essence-valley-glimpse.ngrok-free.dev"

local THEMES = {
    light = {
        bg = Color3.fromRGB(244, 246, 248), panel = Color3.fromRGB(255, 255, 255),
        panelAlt = Color3.fromRGB(237, 240, 243), text = Color3.fromRGB(29, 33, 38),
        muted = Color3.fromRGB(101, 111, 122), border = Color3.fromRGB(211, 216, 222),
        accent = Color3.fromRGB(59, 130, 246), accentHover = Color3.fromRGB(91, 152, 248),
        accentSoft = Color3.fromRGB(229, 239, 255), good = Color3.fromRGB(45, 154, 101),
        goodSoft = Color3.fromRGB(226, 244, 235), bad = Color3.fromRGB(202, 75, 75),
        badSoft = Color3.fromRGB(250, 231, 231), white = Color3.fromRGB(255, 255, 255),
        titlebar = Color3.fromRGB(232, 235, 239), input = Color3.fromRGB(248, 249, 250),
    },
    dark = {
        bg = Color3.fromRGB(32, 35, 39), panel = Color3.fromRGB(42, 46, 51),
        panelAlt = Color3.fromRGB(49, 54, 60), text = Color3.fromRGB(242, 244, 247),
        muted = Color3.fromRGB(155, 166, 178), border = Color3.fromRGB(66, 73, 82),
        accent = Color3.fromRGB(59, 130, 246), accentHover = Color3.fromRGB(91, 152, 248),
        accentSoft = Color3.fromRGB(39, 58, 85), good = Color3.fromRGB(88, 195, 140),
        goodSoft = Color3.fromRGB(35, 68, 54), bad = Color3.fromRGB(230, 106, 106),
        badSoft = Color3.fromRGB(58, 43, 43), white = Color3.fromRGB(255, 255, 255),
        titlebar = Color3.fromRGB(27, 30, 34), input = Color3.fromRGB(34, 38, 43),
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

local titlebar = Instance.new("Frame")
titlebar.Size = UDim2.new(1, 0, 0, 38)
titlebar.BackgroundColor3 = COLORS.titlebar
titlebar.BorderSizePixel = 0
titlebar.Parent = root

local titleLine = Instance.new("Frame")
titleLine.Size = UDim2.new(1, 0, 0, 1)
titleLine.Position = UDim2.new(0, 0, 1, -1)
titleLine.BackgroundColor3 = COLORS.border
titleLine.BorderSizePixel = 0
titleLine.Parent = titlebar

local titleMark = Instance.new("TextLabel")
titleMark.Size = UDim2.fromOffset(22, 22)
titleMark.Position = UDim2.fromOffset(11, 8)
titleMark.BackgroundColor3 = COLORS.accent
titleMark.BorderSizePixel = 0
titleMark.Text = "R"
titleMark.TextColor3 = COLORS.white
titleMark.Font = Enum.Font.GothamBold
titleMark.TextSize = 11
titleMark.Parent = titlebar
local titleMarkCorner = Instance.new("UICorner")
titleMarkCorner.CornerRadius = UDim.new(0, 6)
titleMarkCorner.Parent = titleMark

local titleBrand = Instance.new("TextLabel")
titleBrand.Size = UDim2.new(0, 82, 1, 0)
titleBrand.Position = UDim2.fromOffset(41, 0)
titleBrand.BackgroundTransparency = 1
titleBrand.Text = "RoWatch"
titleBrand.TextColor3 = COLORS.text
titleBrand.TextXAlignment = Enum.TextXAlignment.Left
titleBrand.Font = Enum.Font.GothamBold
titleBrand.TextSize = 12
titleBrand.Parent = titlebar

local titleContext = Instance.new("TextLabel")
titleContext.Size = UDim2.new(1, -224, 1, 0)
titleContext.Position = UDim2.fromOffset(118, 0)
titleContext.BackgroundTransparency = 1
titleContext.Text = "Studio companion"
titleContext.TextColor3 = COLORS.muted
titleContext.TextXAlignment = Enum.TextXAlignment.Left
titleContext.TextTruncate = Enum.TextTruncate.AtEnd
titleContext.Font = Enum.Font.Gotham
titleContext.TextSize = 9
titleContext.Parent = titlebar

local homeButton = Instance.new("TextButton")
homeButton.Size = UDim2.fromOffset(28, 28)
homeButton.AnchorPoint = Vector2.new(1, 0)
homeButton.Position = UDim2.new(1, -43, 0, 5)
homeButton.BackgroundTransparency = 1
homeButton.BorderSizePixel = 0
homeButton.Text = "⌂"
homeButton.TextColor3 = COLORS.muted
homeButton.Font = Enum.Font.GothamBold
homeButton.TextSize = 16
homeButton.Parent = titlebar

local settingsButton = Instance.new("TextButton")
settingsButton.Size = UDim2.fromOffset(28, 28)
settingsButton.AnchorPoint = Vector2.new(1, 0)
settingsButton.Position = UDim2.new(1, -9, 0, 5)
settingsButton.BackgroundTransparency = 1
settingsButton.BorderSizePixel = 0
settingsButton.Text = "⚙"
settingsButton.TextColor3 = COLORS.muted
settingsButton.Font = Enum.Font.GothamBold
settingsButton.TextSize = 15
settingsButton.Parent = titlebar

local scroller = Instance.new("ScrollingFrame")
scroller.Size = UDim2.new(1, 0, 1, -38)
scroller.Position = UDim2.fromOffset(0, 38)
scroller.BackgroundTransparency = 1
scroller.BorderSizePixel = 0
scroller.ScrollBarThickness = 3
scroller.ScrollBarImageColor3 = COLORS.accent
scroller.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroller.CanvasSize = UDim2.new()
scroller.Parent = root

local layout = Instance.new("UIListLayout")
layout.Padding = UDim.new(0, 10)
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Parent = scroller

local padding = Instance.new("UIPadding")
padding.PaddingTop = UDim.new(0, 12)
padding.PaddingBottom = UDim.new(0, 12)
padding.PaddingLeft = UDim.new(0, 12)
padding.PaddingRight = UDim.new(0, 12)
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
local showDocs
local showDocument
local showAuth
local showSettings
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
    round(node, 10)
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
    round(node, 8)
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
    node.BackgroundColor3 = COLORS.input
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
    round(node, 8)
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

local function intro(eyebrow, title, description)
    label(string.upper(eyebrow or "ROWATCH"), 16, COLORS.muted, 9, true)
    label(title, 26, COLORS.text, 18, true)
    if description and description ~= "" then
        label(description, 40, COLORS.muted, 10, false)
    end
end

local function header(subtitle)
    root.BackgroundColor3 = COLORS.bg
    scroller.ScrollBarImageColor3 = COLORS.accent
    titlebar.BackgroundColor3 = COLORS.titlebar
    titleLine.BackgroundColor3 = COLORS.border
    titleMark.BackgroundColor3 = COLORS.accent
    titleMark.TextColor3 = COLORS.white
    titleBrand.TextColor3 = COLORS.text
    titleContext.Text = subtitle or "Studio companion"
    titleContext.TextColor3 = COLORS.muted
    homeButton.TextColor3 = COLORS.muted
    settingsButton.TextColor3 = COLORS.muted
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
    return requestApi("/api/v1/plugin/projects", "GET", nil, {
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


-- Script tracking is strictly session-scoped. No editor text is read or cached
-- until a user explicitly starts a RoWatch session.
local function beginDocumentTracking(document)
    if not sessionId or not activeProfile or documents[document] then return end

    local scriptObject = document:GetScript()
    if not scriptObject then return end

    local ok, text = pcall(function() return document:GetText() end)
    if not ok then return end

    documents[document] = {
        name = scriptObject:GetFullName(),
        startText = text,
        lastText = text,
    }

    apiCall(activeProfile, "/api/v1/events/script/open", "POST", {
        session_id = sessionId,
        script = scriptObject:GetFullName(),
    })
end

local function snapshotOpenDocuments()
    documents = {}
    if not sessionId or not activeProfile then return end

    local ok, openDocuments = pcall(function()
        return ScriptEditorService:GetScriptDocuments()
    end)
    if not ok or not openDocuments then return end

    for _, document in ipairs(openDocuments) do
        beginDocumentTracking(document)
    end
end

local function finishDocumentTracking(document)
    local info = documents[document]
    if not info then return end

    local ok, text = pcall(function() return document:GetText() end)
    if ok then info.lastText = text end

    if sessionId and activeProfile then
        apiCall(activeProfile, "/api/v1/events/script/close", "POST", {
            session_id = sessionId,
            script = info.name,
            chars_added = math.max(#info.lastText - #info.startText, 0),
            chars_removed = math.max(#info.startText - #info.lastText, 0),
        })
    end

    documents[document] = nil
end

local function finishAllDocumentTracking()
    local tracked = {}
    for document in pairs(documents) do
        table.insert(tracked, document)
    end
    for _, document in ipairs(tracked) do
        finishDocumentTracking(document)
    end
    documents = {}
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
        apiCall(activeProfile, "/api/v1/events/instance/change", "POST", {
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
                local _, heartbeatError = apiCall(activeProfile, "/api/v1/events/session/heartbeat", "POST", {session_id = sessionId})
                if heartbeatError then
                    finishAllDocumentTracking()
                    sessionId = nil
                    sessionStart = nil
                    activeProfile = nil
                    instanceQueue = {}
                    documents = {}
                    showProjects("Studio session expired. Start a new session to continue tracking.", true)
                end
            end
        end
    end
end)

showAuth = function(message)
    redraw = function() showAuth() end
    clear()
    header("Connect")
    if message then banner(message, "error") end
    intro("Studio companion", "Connect RoWatch", "Paste your RoWatch account API key to load the projects you can access.")

    local keyCard = card(nil, 12, 9)
    label("ACCOUNT API KEY", 18, COLORS.muted, 9, true, keyCard)
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
    label("Development activity is recorded only after you explicitly start a session.", 34, COLORS.muted, 9, false)
end


showSettings = function(message)
    redraw = function() showSettings() end
    clear()
    header("Account")
    if message then banner(message, "error") end
    intro("RoWatch account", "Plugin settings", "Only settings that matter inside Studio.")

    local accountCard = card(nil, 12, 9)
    label("CONNECTED ACCOUNT", 18, COLORS.muted, 9, true, accountCard)
    label(pluginUsername ~= "" and ("@" .. pluginUsername) or "Not connected", 24, COLORS.text, 13, true, accountCard)
    local themeButton = button(themeName == "dark" and "Use light theme" or "Use dark theme", COLORS.panelAlt, COLORS.text, 36, accountCard)
    themeButton.MouseButton1Click:Connect(function()
        themeName = themeName == "dark" and "light" or "dark"
        COLORS = THEMES[themeName]
        plugin:SetSetting("rw_theme", themeName)
        showSettings()
    end)
    if accountApiKey ~= "" and not sessionId then
        local disconnect = button("Disconnect account", COLORS.badSoft, COLORS.bad, 36, accountCard)
        disconnect.MouseButton1Click:Connect(function()
            accountApiKey = ""
            pluginUsername = ""
            profiles = {}
            plugin:SetSetting("rw_account_api_key", "")
            plugin:SetSetting("rw_account_username", "")
            plugin:SetSetting("rw_projects", profiles)
            showAuth()
        end)
    elseif sessionId then
        label("End the active session before disconnecting this account.", 30, COLORS.muted, 9, false, accountCard)
    end
end

showTasks = function(profile, message)
    redraw = function() showTasks(profile) end
    clear()
    header("My tasks")
    if message then banner(message, message:find("Could not") and "error" or "success") end
    intro(profile.name or "Project", "My tasks", "Only tasks assigned to @" .. pluginUsername .. " appear here.")

    local tasks, err = apiCall(profile, "/api/v1/tasks", "GET")
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
                local _, toggleError = apiCall(profile, "/api/v1/tasks/" .. taskItem.id .. "/complete", "POST", {
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

    local back = button(sessionId and "<  Back to live session" or "<  Back to projects", COLORS.panel, COLORS.muted, 36)
    back.MouseButton1Click:Connect(function()
        if sessionId then showActive() else showProjects() end
    end)
end

showDocument = function(profile, projectDocs, document)
    redraw = function() showDocument(profile, projectDocs, document) end
    clear()
    header("Project docs")
    intro(profile.name or "Project", document.title or "Document", "Read-only project documentation from RoWatch.")

    local contentCard = card(nil, 14, 10)
    label(document.title or "Document", 30, COLORS.text, 16, true, contentCard)
    local content = document.content_md or ""
    content = content:gsub("%[%[([^%]]+)%]%]", "%1 ->")
    content = content:gsub("^#+%s*", ""):gsub("\n#+%s*", "\n")
    local lineCount = 1
    for _ in content:gmatch("\n") do lineCount += 1 end
    local contentHeight = math.clamp(lineCount * 18 + math.ceil(#content / 42) * 12, 54, 430)
    label(content ~= "" and content or "This document is empty.", contentHeight, content ~= "" and COLORS.text or COLORS.muted, 11, false, contentCard)

    if document.links and #document.links > 0 then
        label("LINKED DOCUMENTS", 20, COLORS.muted, 9, true)
        for _, linkItem in ipairs(document.links) do
            local linkedButton = button(linkItem.title .. "  ->", COLORS.panelAlt, COLORS.accent, 36)
            linkedButton.MouseButton1Click:Connect(function()
                for _, candidate in ipairs(projectDocs) do
                    if candidate.id == linkItem.id then
                        showDocument(profile, projectDocs, candidate)
                        return
                    end
                end
                showDocs(profile, "That linked document no longer exists")
            end)
        end
    end

    local back = button("<  Back to project docs", COLORS.panel, COLORS.muted, 36)
    back.MouseButton1Click:Connect(function() showDocs(profile) end)
end

showDocs = function(profile, message)
    redraw = function() showDocs(profile) end
    clear()
    header("Project docs")
    if message then banner(message, "error") end
    intro(profile.name or "Project", "Project docs", "Read and follow linked project documentation.")

    local projectDocs, err = apiCall(profile, "/api/v1/documents", "GET")
    if not projectDocs then
        banner("Could not load docs: " .. (err or "unknown error"), "error")
    elseif #projectDocs == 0 then
        local empty = card()
        label("No project docs", 28, COLORS.text, 14, true, empty)
        label("Documents created on the RoWatch website will appear here.", 38, COLORS.muted, 10, false, empty)
    else
        label(tostring(#projectDocs) .. " DOCUMENT" .. (#projectDocs == 1 and "" or "S"), 18, COLORS.muted, 9, true)
        for _, document in ipairs(projectDocs) do
            local documentCard = card()
            local openButton = button(document.title or "Document", COLORS.panelAlt, COLORS.text, 40, documentCard)
            openButton.TextXAlignment = Enum.TextXAlignment.Left
            addPadding(openButton, 11, 0)
            label("Updated " .. tostring(document.updated_at or "recently"), 20, COLORS.muted, 9, false, documentCard)
            openButton.MouseButton1Click:Connect(function() showDocument(profile, projectDocs, document) end)
        end
    end

    local refresh = button("Refresh docs", COLORS.panelAlt, COLORS.text, 34)
    refresh.MouseButton1Click:Connect(function() showDocs(profile) end)
    local back = button(sessionId and "<  Back to live session" or "<  Back to projects", COLORS.panel, COLORS.muted, 36)
    back.MouseButton1Click:Connect(function()
        if sessionId then showActive() else showProjects() end
    end)
end

showProjects = function(message, isError)
    redraw = function() showProjects() end
    clear()
    header("Projects")
    if message then banner(message, isError and "error" or "success") end
    intro("Connected as @" .. (pluginUsername ~= "" and pluginUsername or "account"), "Your projects", "Choose where you are working, then start a session.")

    if #profiles == 0 then
        local empty = card()
        label("No project memberships", 28, COLORS.text, 14, true, empty)
        label("Join or create a project on the website, then refresh memberships here.", 42, COLORS.muted, 10, false, empty)
    end

    for index, profile in ipairs(profiles) do
        local profileCard = card()
        label(profile.name or "Project", 25, COLORS.text, 14, true, profileCard)
        label("Ready to track  /  " .. (profile.role or "member"), 18, COLORS.muted, 10, false, profileCard)

        local startButton = button("Start session", COLORS.accent, COLORS.white, 40, profileCard)
        startButton.MouseButton1Click:Connect(function()
            startButton.Text = "Connecting..."
            local data, err = apiCall(profile, "/api/v1/events/session/start", "POST")
            if data and data.session_id then
                activeProfile = profile
                sessionId = data.session_id
                sessionStart = os.time()
                lastHeartbeat = 0
                instanceQueue = {}
                snapshotOpenDocuments()
                showActive()
            else
                showProjects("Could not start: " .. (err or "unknown error"), true)
            end
        end)

        local tasksButton = button("My tasks", COLORS.panelAlt, COLORS.text, 34, profileCard)
        tasksButton.MouseButton1Click:Connect(function() showTasks(profile) end)
        local docsButton = button("Project docs", COLORS.panelAlt, COLORS.text, 34, profileCard)
        docsButton.MouseButton1Click:Connect(function() showDocs(profile) end)
    end

    local refresh = button("Refresh projects", COLORS.panelAlt, COLORS.text, 38)
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
        pluginUsername = ""
        profiles = {}
        plugin:SetSetting("rw_account_api_key", "")
        plugin:SetSetting("rw_account_username", "")
        plugin:SetSetting("rw_projects", profiles)
        showAuth()
    end)
    label("Server  " .. ROWATCH_URL, 18, COLORS.muted, 9, false)
end



showActive = function()
    redraw = function() showActive() end
    clear()
    header("Live session")

    local liveCard = card(nil, 14, 8)
    label("●  LIVE SESSION", 20, COLORS.good, 10, true, liveCard)
    label(activeProfile.name or "Active project", 27, COLORS.text, 16, true, liveCard)
    local timer = label("00:00:00", 54, COLORS.text, 34, true, liveCard)
    timer.TextXAlignment = Enum.TextXAlignment.Left
    label("Tracking script activity, code-change counts, parts, and UI changes for this session.", 42, COLORS.muted, 10, false, liveCard)

    local tasksButton = button("View my assigned tasks", COLORS.panel, COLORS.accent, 38)
    tasksButton.MouseButton1Click:Connect(function() showTasks(activeProfile) end)
    local docsButton = button("View project docs", COLORS.panel, COLORS.accent, 38)
    docsButton.MouseButton1Click:Connect(function() showDocs(activeProfile) end)
    local finish = button("End and save session", COLORS.badSoft, COLORS.bad, 42)
    finish.MouseButton1Click:Connect(function()
        finish.Text = "Saving session..."
        flushInstanceQueue()
        finishAllDocumentTracking()
        apiCall(activeProfile, "/api/v1/events/session/end", "POST", {session_id = sessionId})
        sessionId = nil
        sessionStart = nil
        activeProfile = nil
        instanceQueue = {}
        documents = {}
        showProjects("Session saved")
    end)

    task.spawn(function()
        while sessionId and timer.Parent do
            local seconds = os.time() - (sessionStart or os.time())
            timer.Text = string.format("%02d:%02d:%02d",
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
        -- Outside a session, do not read, cache, or send editor contents.
        if not sessionId then return end
        beginDocumentTracking(document)
    end)

    ScriptEditorService.TextDocumentDidChange:Connect(function(document)
        if not sessionId then return end

        local info = documents[document]
        if not info then
            -- Defensive fallback for a document that appeared after the start snapshot.
            beginDocumentTracking(document)
            info = documents[document]
            if not info then return end
        end

        local ok, text = pcall(function() return document:GetText() end)
        if ok then info.lastText = text end
    end)

    ScriptEditorService.TextDocumentDidClose:Connect(function(document)
        if not sessionId then
            documents[document] = nil
            return
        end
        finishDocumentTracking(document)
    end)
end)

homeButton.MouseButton1Click:Connect(function()
    if accountApiKey == "" then showAuth()
    elseif sessionId then showActive()
    else showProjects() end
end)

settingsButton.MouseButton1Click:Connect(function()
    showSettings()
end)

for _, navButton in ipairs({homeButton, settingsButton}) do
    navButton.MouseEnter:Connect(function()
        navButton.BackgroundTransparency = 0
        navButton.BackgroundColor3 = COLORS.panel
        navButton.TextColor3 = COLORS.text
    end)
    navButton.MouseLeave:Connect(function()
        navButton.BackgroundTransparency = 1
        navButton.TextColor3 = COLORS.muted
    end)
    round(navButton, 7)
end

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
        finishAllDocumentTracking()
        apiCall(activeProfile, "/api/v1/events/session/end", "POST", {session_id = sessionId})
    end
end)

if accountApiKey == "" then showAuth() else showProjects() end