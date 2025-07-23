document.addEventListener('DOMContentLoaded', function () {
    console.log('[CHAT.JS] DOM Content Loaded - Initializing chat application');
    console.log('[CHAT.JS] Highlight.js available:', !!hljs);
    
    marked.setOptions({
        breaks: true,
        silent: true
    });

    marked.setOptions({
        breaks: true,
        silent: true,
    });

    marked.use({
        renderer: {
            code(code) {
                console.log('[CHAT.JS] Rendering code block with language:', code['lang']);
                const validLang = hljs.getLanguage(code['lang']) ? code['lang'] : 'plaintext';
                const highlighted = hljs.highlight(code['text'], { language: validLang }).value;
                return `<pre><code class="hljs language-${validLang}">${highlighted}</code></pre>`;
            }
        }
    });

    let accessToken = null;
    let conversations = [];
    let currentConvo = null;
    let messages = [];
    let editingMsgId = null;
    let editingMsgIdx = null;
    let isStreaming = false;
    let tempUserMsg = null;
    let tempAssistantMsg = null;
    let currentLeaf = null;
    let branchPositions = {};
    let currentBranchPositions = {};
    let globalBranchState = {};
    let currentAbortController = null;
    let isStoppingStream = false;
    let backgroundProcessingCheck = null;
    let resumeStreamingCompleted = false; // Flag to track if resume streaming completed successfully

    console.log('[CHAT.JS] Global variables initialized');

    const convosDiv = document.getElementById("convos");
    const messagesDiv = document.getElementById("messages");
    const promptForm = document.getElementById("promptForm");
    const promptInput = document.getElementById("prompt");
    const logoutBtn = document.getElementById("logoutBtn");
    const statusEl = document.getElementById("status");
    const sendButton = promptForm.querySelector('button[type="submit"]');
    const userMenuBtn = document.getElementById("userMenuBtn");
    const userMenuDropdown = document.getElementById("userMenuDropdown");
    const settingsBtn = document.getElementById("settingsBtn");
    const openSidebarBtn = document.getElementById("openSidebarBtn");
    
    console.log('[CHAT.JS] DOM elements found:', {
        convosDiv: !!convosDiv,
        messagesDiv: !!messagesDiv,
        promptForm: !!promptForm,
        promptInput: !!promptInput,
        logoutBtn: !!logoutBtn,
        statusEl: !!statusEl,
        sendButton: !!sendButton,
        userMenuBtn: !!userMenuBtn,
        userMenuDropdown: !!userMenuDropdown,
        settingsBtn: !!settingsBtn,
        openSidebarBtn: !!openSidebarBtn
    });
    
    if (openSidebarBtn) {
        console.log('[CHAT.JS] Setting up sidebar toggle functionality');
        openSidebarBtn.onclick = function() {
            const isClosing = !convosDiv.classList.contains('sidebar-closed');
            console.log('[CHAT.JS] Sidebar toggle clicked, isClosing:', isClosing);
            convosDiv.classList.toggle('sidebar-closed');
            
            if (isClosing) {
                // When closing, delay pointer-events: none to allow animation to be visible
                setTimeout(() => {
                    convosDiv.style.pointerEvents = 'none';
                    console.log('[CHAT.JS] Sidebar pointer events disabled after animation');
                }, 600); // Match the opacity transition duration
            } else {
                // When opening, immediately enable pointer events
                convosDiv.style.pointerEvents = '';
                console.log('[CHAT.JS] Sidebar pointer events enabled');
            }
        };
    }

    // Add CSS for see-more button
    const style = document.createElement('style');
    style.textContent = `
        .see-more-btn {
            background: #27272a;
            color: #a1a1aa;
            border: 1px solid #27272a;
            padding: 0.3rem 0.6rem;
            border-radius: 0;
            cursor: pointer;
            font-size: 0.7rem;
            transition: all 0.2s ease;
            margin-top: 0.5rem;
        }
        
        .see-more-btn:hover {
            background: #313136;
            color: #fff;
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
        }
        
        .modal.show {
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .modal-content {
            background: #232329;
            border: 1px solid #27272a;
            border-radius: 0;
            padding: 2rem;
            width: 90%;
            max-width: 500px;
            max-height: 80vh;
            overflow-y: auto;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }
        
        .modal-title {
            font-size: 1.5rem;
            font-weight: 600;
            color: #e4e4e7;
        }
        
        .close-btn {
            background: none;
            border: none;
            color: #a1a1aa;
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0;
        }
        
        .close-btn:hover {
            color: #fff;
        }
        
        .model-selection-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        
        .model-selection-modal .modal-content {
            background: #232329;
            border-radius: 12px;
            max-width: 800px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            border: 1px solid #27272a;
        }
        
        .model-selection-modal .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem;
            border-bottom: 1px solid #27272a;
        }
        
        .model-selection-modal .modal-header h2 {
            margin: 0;
            color: #e4e4e7;
        }
        
        .model-selection-modal .close-btn {
            background: none;
            border: none;
            color: #71717a;
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0.5rem;
            border-radius: 4px;
        }
        
        .model-selection-modal .close-btn:hover {
            background: #27272a;
            color: #e4e4e7;
        }
        
        .modal-body {
            padding: 1.5rem;
        }
        
        .model-section {
            margin-bottom: 2rem;
        }
        
        .model-section h3 {
            color: #e4e4e7;
            margin-bottom: 1rem;
            font-size: 1.1rem;
        }
        
        .model-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 1rem;
        }
        
        .model-card {
            background: #27272a;
            border: 1px solid #313136;
            border-radius: 8px;
            padding: 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .model-card:hover {
            background: #313136;
            border-color: #52525b;
            transform: translateY(-2px);
        }
        
        .model-card.selected {
            border-color: #3b82f6;
            background: #1e3a8a;
        }
        
        .model-name {
            font-weight: 600;
            color: #e4e4e7;
            margin-bottom: 0.5rem;
        }
        
        .model-description {
            color: #a1a1aa;
            font-size: 0.9rem;
            line-height: 1.4;
        }
        
        .model-stats {
            margin-top: 0.5rem;
            font-size: 0.8rem;
            color: #71717a;
        }
        
        .create-chat-btn {
            background: #3b82f6;
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 6px;
            font-weight: 500;
            cursor: pointer;
            margin-top: 1rem;
            width: 100%;
        }
        
        .create-chat-btn:hover {
            background: #2563eb;
        }
        
        .create-chat-btn:disabled {
            background: #52525b;
            cursor: not-allowed;
        }
        
        .model-selection-interface {
            max-width: 900px;
            margin: 2rem auto;
            padding: 2rem;
            background: #232329;
            border-radius: 12px;
            border: 1px solid #27272a;
        }
        
        .model-selection-header {
            text-align: center;
            margin-bottom: 2rem;
        }
        
        .model-selection-header h2 {
            color: #e4e4e7;
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }
        
        .model-selection-header p {
            color: #a1a1aa;
            font-size: 1rem;
        }
        
        .model-selection-content {
            display: flex;
            flex-direction: column;
            gap: 2.5rem;
        }
        
        .model-selection-footer {
            text-align: center;
            margin-top: 2rem;
        }
        
        .start-chat-btn {
            background: #3b82f6;
            color: white;
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 6px;
            font-weight: 500;
            cursor: pointer;
            font-size: 1rem;
        }
        
        .start-chat-btn:hover {
            background: #2563eb;
        }
        
        .start-chat-btn:disabled {
            background: #52525b;
            cursor: not-allowed;
        }
    `;
    document.head.appendChild(style);

    // --- Auth ---
    async function autoLogin() {
        console.log('[CHAT.JS] Auto-login attempt started');
        try {
            console.log('[CHAT.JS] Fetching auto-login endpoint');
            const res = await fetch("/auto-login");
            if (!res.ok) {
                console.log('[CHAT.JS] Auto-login failed, status:', res.status);
                throw new Error("Not logged in");
            }
            const data = await res.json();
            accessToken = data.access_token;
            console.log('[CHAT.JS] Auto-login successful, access token obtained');
            await loadConversations();
            handleInitialRoute();
        } catch (error) {
            console.log('[CHAT.JS] Auto-login error, redirecting to login:', error.message);
            window.location = "/";
        }
    }

    logoutBtn.onclick = async () => {
        console.log('[CHAT.JS] Logout button clicked');
        try {
            await fetch("/logout", { method: "POST" });
            console.log('[CHAT.JS] Logout successful, redirecting to login');
            window.location = "/";
        } catch (error) {
            console.log('[CHAT.JS] Logout error:', error.message);
            window.location = "/";
        }
    };

    // Add beforeunload event listener to warn user when closing tab during streaming
    window.addEventListener('beforeunload', function(e) {
        if (isStreaming) {
            console.log('[CHAT.JS] Beforeunload event - streaming in progress, showing warning');
            e.preventDefault();
            e.returnValue = 'You have an active conversation. Are you sure you want to leave?';
            return e.returnValue;
        }
    });

    // Add pagehide event listener to detect when page is being unloaded
    window.addEventListener('pagehide', function(e) {
        if (isStreaming) {
            console.log('[CHAT.JS] Page is being unloaded while streaming - this will interrupt the response');
            // The browser will automatically abort the fetch request
        }
    });

    // --- Conversations ---
    async function loadConversations() {
        console.log('[CHAT.JS] Loading conversations');
        try {
            const res = await fetch("/api/conversations", {
                headers: { Authorization: "Bearer " + accessToken }
            });
            if (!res.ok) {
                console.log('[CHAT.JS] Failed to load conversations, status:', res.status);
                throw new Error(`HTTP ${res.status}`);
            }
            conversations = await res.json();
            console.log('[CHAT.JS] Conversations loaded successfully, count:', conversations.length);
            renderConvos();
        } catch (error) {
            console.log('[CHAT.JS] Error loading conversations:', error.message);
        }
    }

    function renderConvos() {
        console.log('[CHAT.JS] Rendering conversations, count:', conversations.length);
        convosDiv.innerHTML = '';

        // Remove the close button at the top (no longer needed)

        const newChat = document.createElement("a");
        newChat.href = "/chat/new";
        newChat.textContent = "+ New Chat";
        newChat.className = "new-chat-btn";
        newChat.onclick = (e) => {
            e.preventDefault();
            console.log('[CHAT.JS] New chat button clicked');
            newConvo();
        };
        convosDiv.appendChild(newChat);
        convosDiv.appendChild(document.createElement("hr"));
        conversations.forEach(c => {
            console.log('[CHAT.JS] Rendering conversation:', c.conversation_id, 'title:', c.title);
            const row = document.createElement("div");
            row.className = "convo-row";
            const a = document.createElement("a");
            a.href = `/chat/${c.conversation_id}`;
            a.textContent = c.title || "Untitled";
            a.className = (currentConvo === c.conversation_id) ? "selected" : "";
            a.onclick = (e) => {
                e.preventDefault();
                console.log('[CHAT.JS] Conversation clicked:', c.conversation_id);
                navigateToConvo(c.conversation_id);
            };
            row.appendChild(a);

            const renameBtn = document.createElement("button");
            renameBtn.textContent = "✏️";
            renameBtn.className = "rename-btn";
            renameBtn.title = "Rename";
            renameBtn.onclick = async (e) => {
                e.stopPropagation();
                e.preventDefault();
                console.log('[CHAT.JS] Rename button clicked for conversation:', c.conversation_id);
                const newTitle = prompt("Enter new title:", c.title || "");
                if (newTitle && newTitle !== c.title) {
                    console.log('[CHAT.JS] Renaming conversation from:', c.title, 'to:', newTitle);
                    try {
                        await fetch(`/api/conversations/${c.conversation_id}/title`, {
                            method: "PUT",
                            headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                            body: JSON.stringify(newTitle)
                        });
                        c.title = newTitle;
                        renderConvos();
                        console.log('[CHAT.JS] Conversation renamed successfully');
                    } catch (error) {
                        console.log('[CHAT.JS] Error renaming conversation:', error.message);
                    }
                }
            };
            row.appendChild(renameBtn);

            convosDiv.appendChild(row);
        });
        console.log('[CHAT.JS] Conversations rendering completed');
    }

    function navigateToConvo(convoId) {
        console.log('[CHAT.JS] Navigating to conversation:', convoId);
        if (!convoId) {
            console.log('[CHAT.JS] No conversation ID provided, skipping navigation');
            return;
        }
        history.pushState({ convoId }, "", `/chat/${convoId}`);
        console.log('[CHAT.JS] History state updated, opening conversation');
        openConvo(convoId);
    }

    window.newConvo = async function () {
        console.log('[CHAT.JS] New conversation function called');
        // Stop any background processing polling
        if (backgroundProcessingCheck) {
            console.log('[CHAT.JS] Clearing background processing check interval');
            clearInterval(backgroundProcessingCheck);
            backgroundProcessingCheck = null;
        }
        
        console.log('[CHAT.JS] Resetting conversation state');
        window.lastNonEmptyMessages = null;
        window.lastConversationId = null;
        messages = [];
        tempUserMsg = null;
        tempAssistantMsg = null;
        isStreaming = false;

        // Create chat without model selection
        console.log('[CHAT.JS] Creating new chat without model selection');
        await createChatWithoutModel();
    };

    async function showModelSelectionModal() {
        console.log('[CHAT.JS] Showing model selection modal');
        try {
            // Get model suggestions
            console.log('[CHAT.JS] Fetching model suggestions');
            const suggestionsResponse = await fetch("/api/analytics/model-suggestions", {
                headers: { Authorization: "Bearer " + accessToken }
            });
            if (!suggestionsResponse.ok) {
                console.log('[CHAT.JS] Failed to fetch model suggestions, status:', suggestionsResponse.status);
                throw new Error(`HTTP ${suggestionsResponse.status}`);
            }
            const suggestions = await suggestionsResponse.json();
            console.log('[CHAT.JS] Model suggestions received:', suggestions);
            
            // Create modal
            const modal = document.createElement("div");
            modal.className = "model-selection-modal";
            modal.innerHTML = `
                <div class="modal-content">
                    <div class="modal-header">
                        <h2>Choose Your Model</h2>
                        <button class="close-btn" onclick="this.closest('.model-selection-modal').remove()">×</button>
                    </div>
                    <div class="modal-body">
                        <div class="model-section">
                            <h3>🔥 Trending</h3>
                            <div class="model-grid" id="trending-models"></div>
                        </div>
                        <div class="model-section">
                            <h3>📚 Recently Used</h3>
                            <div class="model-grid" id="used-models"></div>
                        </div>
                        <div class="model-section">
                            <h3>🆕 New Models</h3>
                            <div class="model-grid" id="new-models"></div>
                        </div>
                        <div class="model-section">
                            <h3>💡 Recommended</h3>
                            <div class="model-grid" id="recommended-models"></div>
                        </div>
                    </div>
                </div>
            `;
            
            // Populate sections
            populateModelSection('trending-models', suggestions.trending, 'trending');
            populateModelSection('used-models', suggestions.used, 'used');
            populateModelSection('new-models', suggestions.new, 'new');
            
            // Get recommended models
            const recommendedResponse = await fetch("/api/analytics/recommended?limit=5", {
                headers: { Authorization: "Bearer " + accessToken }
            });
            const recommended = await recommendedResponse.json();
            populateModelSection('recommended-models', recommended, 'recommended');
            
            // Add create chat button
            const createBtn = document.createElement("button");
            createBtn.className = "create-chat-btn";
            createBtn.textContent = "Start Chatting";
            createBtn.disabled = true;
            createBtn.onclick = () => createChatWithSelectedModel();
            modal.querySelector(".modal-body").appendChild(createBtn);
            
            // Store selected model
            window.selectedModelId = null;
            
            document.body.appendChild(modal);
            
        } catch (error) {
            console.error("Error showing model selection:", error);
            // Fallback to creating chat without model selection
            createChatWithoutModel();
        }
    }

    async function showModelSelectionInMessages() {
        try {
            // Get model suggestions
            const suggestionsResponse = await fetch("/api/analytics/model-suggestions", {
                headers: { Authorization: "Bearer " + accessToken }
            });
            const suggestions = await suggestionsResponse.json();
            
            console.log("Model suggestions received:", suggestions);
            
            // Create model selection interface
            const modelSelectionDiv = document.createElement("div");
            modelSelectionDiv.className = "model-selection-interface";
            modelSelectionDiv.innerHTML = `
                <div class="model-selection-header">
                    <h2>Choose Your Model</h2>
                    <p>Select a model to start chatting</p>
                </div>
                <div class="model-selection-content">
                    <div class="model-section">
                        <h3>🔥 Trending</h3>
                        <div class="model-grid" id="trending-models"></div>
                    </div>
                    <div class="model-section">
                        <h3>📚 Recently Used</h3>
                        <div class="model-grid" id="used-models"></div>
                    </div>
                    <div class="model-section">
                        <h3>💡 Recommended</h3>
                        <div class="model-grid" id="recommended-models"></div>
                    </div>
                </div>
                <div class="model-selection-footer">
                    <button class="start-chat-btn" disabled>Start Chatting</button>
                </div>
            `;
            
            // Store suggestions globally for the "see more" modal
            window.modelSuggestions = suggestions;
            
            // Add to messages area FIRST
            const messagesDiv = document.getElementById('messages');
            if (messagesDiv) {
                messagesDiv.appendChild(modelSelectionDiv);
                
                // THEN populate sections after DOM is updated
                populateModelSection('trending-models', suggestions.trending, 'trending');
                populateModelSection('used-models', suggestions.used, 'used');
                populateModelSection('recommended-models', suggestions.recommended, 'recommended');
            }
            
            // Add event listener for start chat button
            const startBtn = modelSelectionDiv.querySelector('.start-chat-btn');
            startBtn.onclick = () => createChatWithSelectedModel();
            
            // Store selected model
            window.selectedModelId = null;
            
        } catch (error) {
            console.error("Error showing model selection:", error);
            // Fallback to creating chat without model selection
            createChatWithoutModel();
        }
    }
    
    function populateModelSection(containerId, models, category) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Container ${containerId} not found`);
            return;
        }
        
        console.log(`Populating ${category} section with ${models.length} models:`, models);
        
        if (!models || models.length === 0) {
            container.innerHTML = '<p style="color: #71717a; font-style: italic;">No models available</p>';
            return;
        }
        
        models.forEach(model => {
            const card = document.createElement("div");
            card.className = "model-card";
            card.onclick = () => selectModel(model.model_id, card);
            
            let stats = '';
            if (category === 'trending' && model.usage_count) {
                stats = `${model.usage_count} uses this week`;
            } else if (category === 'used' && model.last_used) {
                const date = new Date(model.last_used);
                stats = `Last used ${date.toLocaleDateString()}`;
            } else if (category === 'new') {
                const date = new Date(model.created_at);
                stats = `Added ${date.toLocaleDateString()}`;
            } else if (category === 'recommended' && model.usage_count) {
                stats = `${model.usage_count} uses this week`;
            }
            
            const hasLongDescription = model.long_description && model.long_description.trim() !== '';
            
            card.innerHTML = `
                <div class="model-name">${model.name}</div>
                <div class="model-description">${model.short_description || 'No description available'}</div>
                ${stats ? `<div class="model-stats">${stats}</div>` : ''}
                ${hasLongDescription ? `<button class="see-more-btn" onclick="event.stopPropagation(); showModelDetails('${model.model_id}')">See more</button>` : ''}
            `;
            
            container.appendChild(card);
        });
    }
    
    function selectModel(modelId, card) {
        console.log('[CHAT.JS] Model selected:', modelId);
        // Remove previous selection
        document.querySelectorAll('.model-card.selected').forEach(c => c.classList.remove('selected'));
        
        // Select new model
        card.classList.add('selected');
        window.selectedModelId = modelId;
        console.log('[CHAT.JS] Model selection updated, selectedModelId:', window.selectedModelId);
        
        // Enable create button
        const createBtn = document.querySelector('.create-chat-btn');
        if (createBtn) {
            createBtn.disabled = false;
            console.log('[CHAT.JS] Create chat button enabled');
        }
        
        // Enable start chat button
        const startBtn = document.querySelector('.start-chat-btn');
        if (startBtn) {
            startBtn.disabled = false;
            console.log('[CHAT.JS] Start chat button enabled');
        }
    }
    
    async function createChatWithSelectedModel() {
        console.log('[CHAT.JS] Creating chat with selected model:', window.selectedModelId);
        if (!window.selectedModelId) {
            console.log('[CHAT.JS] No model selected, returning');
            return;
        }
        
        try {
            // Update the current conversation with the selected model
            console.log('[CHAT.JS] Updating conversation with model ID');
            const res = await fetch(`/api/conversations/${currentConvo}`, {
                method: "PUT",
                headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                body: JSON.stringify({
                    model_id: window.selectedModelId
                })
            });
            
            if (res.ok) {
                console.log('[CHAT.JS] Conversation updated successfully with model');
                // Track usage for the selected model
                console.log('[CHAT.JS] Tracking model usage');
                await fetch("/api/analytics/usage", {
                    method: "POST",
                    headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                    body: JSON.stringify({
                        model_id: window.selectedModelId,
                        conversation_id: currentConvo,
                        usage_type: "conversation_start",
                        usage_count: 1
                    })
                });
                
                // Remove the model selection interface
                const modelSelectionInterface = document.querySelector('.model-selection-interface');
                if (modelSelectionInterface) {
                    modelSelectionInterface.remove();
                    console.log('[CHAT.JS] Model selection interface removed');
                }
                
                // Refresh the conversation to show model info
                console.log('[CHAT.JS] Refreshing conversation to show model info');
                await openConvo(currentConvo);
            } else {
                console.log('[CHAT.JS] Failed to update conversation, status:', res.status);
            }
        } catch (error) {
            console.log('[CHAT.JS] Error updating conversation with model:', error.message);
        }
    }
    
    async function createChatWithoutModel() {
        console.log('[CHAT.JS] Creating new chat without model');
        try {
            const res = await fetch("/api/conversations", {
                method: "POST",
                headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: "New chat"
                })
            });
            if (!res.ok) {
                console.log('[CHAT.JS] Failed to create conversation, status:', res.status);
                throw new Error(`HTTP ${res.status}`);
            }
            const convo = await res.json();
            console.log('[CHAT.JS] New conversation created:', convo.conversation_id);
            conversations.unshift(convo);
            renderConvos();
            if (convo.conversation_id) {
                navigateToConvo(convo.conversation_id);
            }
        } catch (error) {
            console.log('[CHAT.JS] Error creating new chat:', error.message);
        }
    }

    // --- Messages ---
    async function openConvo(convoId) {
        console.log('[CHAT.JS] Opening conversation:', convoId);
        if (!convoId) {
            console.log('[CHAT.JS] No conversation ID provided, returning');
            return;
        }
        
        // Stop any background processing polling for the previous conversation
        if (backgroundProcessingCheck) {
            console.log('[CHAT.JS] Clearing background processing check for previous conversation');
            clearInterval(backgroundProcessingCheck);
            backgroundProcessingCheck = null;
        }
        
        currentConvo = convoId;
        console.log('[CHAT.JS] Current conversation set to:', currentConvo);
        renderConvos();

        console.log('[CHAT.JS] Resetting conversation state');
        window.lastNonEmptyMessages = null;
        window.lastConversationId = null;

        // Preserve the current prompt if we're stopping a stream
        const currentPrompt = isStoppingStream ? promptInput.innerText : null;
        if (isStoppingStream) {
            console.log('[CHAT.JS] Preserving current prompt during stream stop');
        }

        console.log('[CHAT.JS] Fetching conversation data');
        const [branchMsgs, convo] = await Promise.all([
            fetch(`/api/conversations/${convoId}/messages`, {
                headers: { Authorization: "Bearer " + accessToken }
            }).then(r => r.json()),
            fetch(`/api/conversations/${convoId}/meta`, {
                headers: { Authorization: "Bearer " + accessToken }
            }).then(r => r.json())
        ]);

        messages = branchMsgs;
        console.log('[CHAT.JS] Messages loaded, count:', messages.length);
        currentLeaf = convo.current_leaf_message_id || (messages.length ? messages[messages.length - 1].message_id : null);
        console.log('[CHAT.JS] Current leaf message ID:', currentLeaf);

        // Get model information if available
        let modelInfo = null;
        if (convo.model_id) {
            console.log('[CHAT.JS] Fetching model info for model ID:', convo.model_id);
            try {
                const modelResponse = await fetch(`/api/models/${convo.model_id}`, {
                    headers: { Authorization: "Bearer " + accessToken }
                });
                if (modelResponse.ok) {
                    modelInfo = await modelResponse.json();
                    console.log('[CHAT.JS] Model info loaded:', modelInfo.name);
                } else {
                    console.log('[CHAT.JS] Failed to fetch model info, status:', modelResponse.status);
                }
            } catch (error) {
                console.log('[CHAT.JS] Error fetching model info:', error.message);
            }
        } else {
            console.log('[CHAT.JS] No model ID in conversation');
        }
        window.currentModelInfo = modelInfo;

        // Check if there's ongoing background processing for this conversation
        console.log('[CHAT.JS] Checking background processing status');
        try {
            // Skip background processing check if resume streaming just completed
            if (resumeStreamingCompleted) {
                console.log('[CHAT.JS] Resume streaming completed, skipping background processing check');
                resumeStreamingCompleted = false; // Reset flag
                tempUserMsg = null;
                tempAssistantMsg = null;
            } else {
                console.log('[CHAT.JS] Fetching processing status');
                const processingStatus = await fetch(`/api/conversations/${convoId}/processing-status`, {
                    headers: { Authorization: "Bearer " + accessToken }
                });
                const status = await processingStatus.json();
                console.log('[CHAT.JS] Processing status:', status);
                
                if (status.processing) {
                    console.log('[CHAT.JS] Detected ongoing background processing, starting real-time streaming');
                    // Create a temporary assistant message to show background processing
                    tempAssistantMsg = { 
                        role: "assistant", 
                        content: "*[Response is being completed in background...]*",
                        message_id: null 
                    };
                    // Start real-time streaming instead of polling
                    startResumeStreaming();
                } else {
                    console.log('[CHAT.JS] No background processing detected, loading conversation normally');
                    // No background processing - load the conversation normally
                    // Clear any temporary messages
                    tempUserMsg = null;
                    tempAssistantMsg = null;
                    
                    // Check if the last message is a user message without a corresponding assistant message
                    // This indicates an interrupted stream that wasn't handled by background processing
                    if (messages.length > 0 && messages[messages.length - 1].role === 'user') {
                        console.log('[CHAT.JS] Detected interrupted stream - last message is user message');
                        // Create a temporary assistant message to show "Response in progress..."
                        tempAssistantMsg = { 
                            role: "assistant", 
                            content: "*[Response was interrupted - you can continue the conversation]*",
                            message_id: null 
                        };
                    }
                }
            }
        } catch (error) {
            console.log('[CHAT.JS] Error checking background processing status:', error.message);
            // Fallback to the original logic
            if (messages.length > 0 && messages[messages.length - 1].role === 'user') {
                console.log('[CHAT.JS] Fallback: Detected interrupted stream - last message is user message');
                tempAssistantMsg = { 
                    role: "assistant", 
                    content: "*[Response was interrupted - you can continue the conversation]*",
                    message_id: null 
                };
            } else {
                tempUserMsg = null;
                tempAssistantMsg = null;
            }
        }
        
        isStreaming = false;
        console.log('[CHAT.JS] Streaming state reset to false');

        console.log('[CHAT.JS] Rendering messages');
        renderMessages();
        // promptForm.style.display = "block";
        
        // Restore the prompt if we were stopping a stream
        if (isStoppingStream && currentPrompt) {
            console.log('[CHAT.JS] Restoring prompt after stream stop');
            promptInput.innerText = currentPrompt;
        }
        
        isStoppingStream = false;
        console.log('[CHAT.JS] Conversation opened successfully');
    }

    function renderMessages() {
        console.log('[CHAT.JS] Rendering messages, count:', messages.length, 'streaming:', isStreaming);
        const wasAtBottom = messagesDiv.scrollTop + messagesDiv.clientHeight >= messagesDiv.scrollHeight - 10;
        messagesDiv.innerHTML = "";
        if (!messages.length && isStreaming && window.lastNonEmptyMessages && window.lastConversationId === currentConvo) {
            console.log('[CHAT.JS] Restoring last non-empty messages during streaming');
            messages = window.lastNonEmptyMessages;
        }
        if (messages.length) {
            window.lastNonEmptyMessages = [...messages];
            window.lastConversationId = currentConvo;
            console.log('[CHAT.JS] Updated last non-empty messages, count:', window.lastNonEmptyMessages.length);
        }
        
        // Show placeholder message for new chats
        if (!messages.length && !tempUserMsg && !tempAssistantMsg) {
            // Check if we already have a model selected
            if (window.currentModelInfo) {
                // Show model info placeholder
                const placeholderDiv = document.createElement("div");
                placeholderDiv.className = "msg assistant placeholder-message";
                placeholderDiv.style.position = "absolute";
                placeholderDiv.style.top = "40%";
                placeholderDiv.style.left = "50%";
                placeholderDiv.style.transform = "translate(-50%, -50%)";
                placeholderDiv.style.textAlign = "center";
                placeholderDiv.style.padding = "0";
                placeholderDiv.style.color = "#ffffff";
                placeholderDiv.style.fontSize = "2rem";
                placeholderDiv.style.fontWeight = "500";
                placeholderDiv.style.background = "transparent";
                placeholderDiv.style.border = "none";
                placeholderDiv.style.margin = "0";
                placeholderDiv.style.width = "auto";
                placeholderDiv.style.minWidth = "300px";
                placeholderDiv.style.maxWidth = "600px";
                placeholderDiv.style.zIndex = "10";
                
                placeholderDiv.innerHTML = `
                    <div style="margin-bottom: 1rem;">
                        <div style="font-size: 1.2rem; color: #a1a1aa; margin-bottom: 0.5rem;">
                            Using: <strong style="color: #3b82f6;">${window.currentModelInfo.name}</strong>
                        </div>
                        ${window.currentModelInfo.description ? 
                            `<div style="font-size: 0.9rem; color: #71717a; margin-bottom: 1rem;">${window.currentModelInfo.description}</div>` : 
                            ''
                        }
                    </div>
                    <div style="font-size: 1.5rem;">How can I help you?</div>
                `;
                
                messagesDiv.appendChild(placeholderDiv);
            } else {
                // Show model selection interface directly in the messages area
                showModelSelectionInMessages();
            }
            return;
        }

        let allMessages = [...messages];
        if (tempUserMsg) allMessages.push(tempUserMsg);
        if (tempAssistantMsg) allMessages.push(tempAssistantMsg);

        let messagesWithSiblings = [];
        allMessages.forEach((msg, idx) => {
            if (msg.role === 'user' && msg.siblings && msg.siblings.length > 0) {
                let currentPosition = 0;
                const currentMessageInPath = allMessages.some(m => m.message_id === msg.message_id);

                if (!currentMessageInPath) {
                    for (let i = 0; i < msg.siblings.length; i++) {
                        const sibling = msg.siblings[i];
                        const siblingInPath = allMessages.some(m => m.message_id === sibling.message_id);
                        if (siblingInPath) {
                            currentPosition = i + 1;
                            break;
                        }
                    }
                }

                messagesWithSiblings.push({
                    message: msg,
                    index: idx,
                    currentPosition: currentPosition,
                    totalBranches: msg.siblings.length + 1
                });

                const branchKey = `${msg.content.substring(0, 20)}_${msg.parent_message_id || 'root'}`;
                globalBranchState[branchKey] = currentPosition;
            }
        });

        allMessages.forEach((msg, idx) => {
            const div = document.createElement("div");
            div.className = `msg ${msg.role}`;
            if (msg === tempAssistantMsg) {
                div.id = 'streaming-message';
                const textSpan = document.createElement("span");
                textSpan.id = 'streaming-content';
                textSpan.innerHTML = marked.parse(msg.content);
                div.appendChild(textSpan);
            } else if (msg.role === 'user') {
                const innerBubble = document.createElement("span");
                innerBubble.className = "inner-bubble";
                innerBubble.style.whiteSpace = 'pre-wrap';
                if (editingMsgId === msg.message_id) {
                    const editInput = document.createElement("div");
                    editInput.contentEditable = true;
                    editInput.innerText = msg.content;
                    editInput.className = "edit-inline-input";
                    editInput.style.width = "80%";
                    editInput.style.maxHeight = "200px";
                    editInput.style.overflow = "auto";
                    editInput.style.marginRight = "0.5rem";
                    innerBubble.appendChild(editInput);

                    // Focus the edit input after it's rendered
                    setTimeout(() => {
                        editInput.focus();
                        // Place cursor at the end of the text
                        const range = document.createRange();
                        const selection = window.getSelection();
                        range.selectNodeContents(editInput);
                        range.collapse(false); // false means collapse to end
                        selection.removeAllRanges();
                        selection.addRange(range);
                    }, 0);

                    function saveEditInline() {
                        const new_content = editInput.innerText.trim();
                        if (!new_content) return;
                        editingMsgId = null;
                        editMessage(msg.message_id, new_content);
                    }

                    editInput.addEventListener('keydown', function (e) {
                        if (e.key === 'Escape') {
                            editingMsgId = null;
                            renderMessages();
                        } else if (e.key === 'Enter' && !e.ctrlKey) {
                            e.preventDefault();
                            saveEditInline();
                        }
                    });

                    const saveBtn = document.createElement("button");
                    saveBtn.textContent = "💾";
                    saveBtn.className = "edit-inline-save";
                    saveBtn.onclick = saveEditInline;
                    innerBubble.appendChild(saveBtn);

                    const cancelBtn = document.createElement("button");
                    cancelBtn.textContent = "✖️";
                    cancelBtn.className = "edit-inline-cancel";
                    cancelBtn.onclick = () => {
                        editingMsgId = null;
                        renderMessages();
                    };
                    innerBubble.appendChild(cancelBtn);
                } else {
                    innerBubble.textContent = `You: ${msg.content}`;
                }
                div.appendChild(innerBubble);
            } else {
                const textSpan = document.createElement("span");
                textSpan.innerHTML = marked.parse(msg.content);
                div.appendChild(textSpan);
            }

            let controlsDiv = null;
            if (msg.role === 'user' && !isStreaming) {
                controlsDiv = document.createElement("div");
                controlsDiv.className = "controls-container";

                const branchGroup = document.createElement("span");
                branchGroup.className = "branch-group";

                const editBtn = document.createElement("button");
                editBtn.innerHTML = "✏️";
                editBtn.className = "edit-btn";
                editBtn.title = "Edit";
                editBtn.onclick = () => {
                    startEdit(msg, idx);
                };
                branchGroup.appendChild(editBtn);

                if (msg.siblings && msg.siblings.length > 0) {
                    const allBranches = [msg, ...msg.siblings];
                    allBranches.sort((a, b) => a.order_index - b.order_index);

                    let activeBranchIdx = allBranches.findIndex(branch =>
                        allMessages.some(m => m.message_id === branch.message_id)
                    );
                    if (activeBranchIdx === -1) activeBranchIdx = 0;

                    const leftArrow = document.createElement("button");
                    leftArrow.textContent = "←";
                    leftArrow.className = "branch-arrow";
                    leftArrow.title = "Previous branch";

                    const counter = document.createElement("span");
                    counter.className = "branch-counter";
                    counter.textContent = `${activeBranchIdx + 1} / ${allBranches.length}`;

                    const rightArrow = document.createElement("button");
                    rightArrow.textContent = "→";
                    rightArrow.className = "branch-arrow";
                    rightArrow.title = "Next branch";

                    const navigateToBranch = (targetIdx) => {
                        const targetMessageId = allBranches[targetIdx].message_id;
                        fetch(`/api/messages/${targetMessageId}/leaf`, {
                            headers: { Authorization: "Bearer " + accessToken }
                        })
                            .then(leafRes => leafRes.ok ? leafRes.json() : Promise.reject('Failed to get leaf'))
                            .then(leafData => setCurrentLeaf(currentConvo, leafData.leaf_message_id))
                            .then(() => openConvo(currentConvo))
                            .catch(error => console.error("Error switching branch:", error));
                    };
                    leftArrow.onclick = () => {
                        const newIdx = (activeBranchIdx === 0) ? allBranches.length - 1 : activeBranchIdx - 1;
                        navigateToBranch(newIdx);
                    };
                    rightArrow.onclick = () => {
                        const newIdx = (activeBranchIdx === allBranches.length - 1) ? 0 : activeBranchIdx + 1;
                        navigateToBranch(newIdx);
                    };

                    branchGroup.appendChild(leftArrow);
                    branchGroup.appendChild(counter);
                    branchGroup.appendChild(rightArrow);
                }
                controlsDiv.appendChild(branchGroup);
            }
            if (controlsDiv) {
                div.appendChild(controlsDiv);
            }
            messagesDiv.appendChild(div);
        });

        if (wasAtBottom) {
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
    }

    async function setCurrentLeaf(convoId, leafMsgId) {
        await fetch(`/api/conversations/${convoId}/leaf`, {
            method: "PUT",
            headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
            body: JSON.stringify({ message_id: leafMsgId })
        });
    }


    function marked_parse(content) {
        return marked.parse(content);
    }

    async function sendPromptStream(prompt) {
        console.log('[CHAT.JS] sendPromptStream called with prompt length:', prompt?.length, 'conversation:', currentConvo);
        if (!prompt || !currentConvo) {
            console.log('[CHAT.JS] Missing prompt or conversation ID, returning');
            return;
        }
        
        // Reset the stopping flag when starting a new stream
        isStoppingStream = false;
        console.log('[CHAT.JS] Reset stopping flag, starting new stream');
        
        // Only clear the prompt input if we're not stopping a stream
        if (!isStoppingStream) {
            promptInput.innerHTML = "";
            console.log('[CHAT.JS] Cleared prompt input');
        }

        let parent_message_id = null;
        console.log('[CHAT.JS] Parent message ID:', parent_message_id);

        tempUserMsg = { role: "user", content: prompt, parent_message_id };
        tempAssistantMsg = { role: "assistant", content: "", parent_message_id: null };
        isStreaming = true;
        console.log('[CHAT.JS] Created temporary messages, streaming set to true');
        updateSendButtonState();
        renderMessages(); // Render once at the start

        // Create new AbortController for this request
        currentAbortController = new AbortController();
        console.log('[CHAT.JS] Created new AbortController for stream request');

        try {
            console.log('[CHAT.JS] Sending stream request to API');
            const response = await fetch(`/api/conversations/${currentConvo}/messages/stream`, {
                method: "POST",
                headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                body: JSON.stringify({ prompt, parent_message_id }),
                signal: currentAbortController.signal
            });

            if (!response.ok) {
                console.log('[CHAT.JS] Stream request failed, status:', response.status);
                throw new Error(`HTTP ${response.status}`);
            }

            console.log('[CHAT.JS] Stream request successful, starting to read response');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let shouldReload = false;
            console.log('[CHAT.JS] Stream reader and decoder initialized');
            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    console.log('[CHAT.JS] Stream reading completed');
                    break;
                }
                buffer += decoder.decode(value, { stream: true });
                let parts = buffer.split("\n\n");
                buffer = parts.pop();
                console.log('[CHAT.JS] Processing stream parts, count:', parts.length);
                for (const part of parts) {
                    if (part.startsWith("data: ")) {
                        const token = part.slice(6);
                        console.log('[CHAT.JS] Processing token:', token.substring(0, 50) + (token.length > 50 ? '...' : ''));
                        if (token === "[DONE]" || token === "[INTERRUPTED]") {
                            console.log('[CHAT.JS] Received stream end signal:', token);
                            break;
                        }
                        if (token === "[SAVED]") {
                            console.log('[CHAT.JS] Received [SAVED] signal from backend, reloading conversation');
                            shouldReload = true;
                            break;
                        }
                        if (token === "[CONTINUING_IN_BACKGROUND]") {
                            console.log('[CHAT.JS] Received [CONTINUING_IN_BACKGROUND] signal - response will be completed in background');
                            tempAssistantMsg.content += "\n\n*[Response will be completed in background]*";
                            renderMessages();
                            shouldReload = true;
                            // Start polling for background processing completion
                            startBackgroundProcessingPolling();
                            break;
                        }
                        
                        // Check if this is a title message
                        try {
                            const parsedToken = JSON.parse(token);
                            if (parsedToken.message && parsedToken.message.title) {
                                // This is a title message - update the conversation title
                                console.log('[CHAT.JS] Received title:', parsedToken.message.title);
                                const currentConvoObj = conversations.find(c => c.conversation_id === currentConvo);
                                if (currentConvoObj) {
                                    currentConvoObj.title = parsedToken.message.title;
                                    renderConvos(); // Update the sidebar
                                    
                                    // Save the title to the database
                                    fetch(`/api/conversations/${currentConvo}/save-title`, {
                                        method: "POST",
                                        headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                                        body: JSON.stringify({ title: parsedToken.message.title })
                                    }).then(res => {
                                        if (res.ok) {
                                            console.log('[CHAT.JS] Title saved to database');
                                        } else {
                                            console.log('[CHAT.JS] Failed to save title to database, status:', res.status);
                                        }
                                    }).catch(err => {
                                        console.log('[CHAT.JS] Error saving title:', err.message);
                                    });
                                }
                                continue; // Skip adding this to the assistant message content
                            }
                        } catch (e) {
                            // Not a JSON object, treat as regular token
                            console.log('[CHAT.JS] Token is not JSON, treating as regular token');
                        }
                        
                        // Regular token - add to assistant message
                        try {
                            const parsedToken = JSON.parse(token);
                            tempAssistantMsg.content += parsedToken;
                            console.log('[CHAT.JS] Added token to assistant message, content length:', tempAssistantMsg.content.length);
                            const streamingContent = document.getElementById('streaming-content');
                            if (streamingContent) {
                                const isAtBottom = messagesDiv.scrollTop + messagesDiv.clientHeight >= messagesDiv.scrollHeight - 10;
                                streamingContent.innerHTML = marked.parse(tempAssistantMsg.content);
                                if (isAtBottom) {
                                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                                }
                            }
                        } catch (parseError) {
                            console.log('[CHAT.JS] Error parsing token as JSON:', parseError.message, 'token:', token);
                        }
                    }
                }
                if (shouldReload) break;
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('[CHAT.JS] Stream was aborted by user');
                if (tempAssistantMsg && tempAssistantMsg.content) {
                    tempAssistantMsg.content += "\n\n*[Response stopped by user]*";
                    renderMessages();
                    // Fallback: save the partial response directly to DB
                    console.log('[CHAT.JS] Saving partial response after abort');
                    await savePartialResponse(tempAssistantMsg.content);
                }
            } else {
                console.log('[CHAT.JS] Stream error:', error.message);
            }
        } finally {
            console.log('[CHAT.JS] Stream finally block - cleaning up');
            isStreaming = false;
            currentAbortController = null;
            updateSendButtonState();
            if (isStoppingStream) {
                console.log('[CHAT.JS] Stream was stopped, keeping partial response');
                // Don't clear tempAssistantMsg, keep the partial response
            } else {
                console.log('[CHAT.JS] Stream completed normally, clearing temporary messages');
                tempUserMsg = null;
                tempAssistantMsg = null;
                await openConvo(currentConvo);
            }
            editingMsgId = null;
            editingMsgIdx = null;
            console.log('[CHAT.JS] Stream cleanup completed');
        }
    }

    promptInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!isStreaming) {
                promptForm.requestSubmit();
            }
        }
    });

    promptForm.onsubmit = async (e) => {
        console.log('[CHAT.JS] Form submission triggered');
        e.preventDefault();
        if (isStreaming) {
            console.log('[CHAT.JS] Currently streaming, stopping stream instead of submitting');
            // If streaming, stop the stream instead of submitting
            stopStream();
            return;
        }
        const prompt = promptInput.innerText.trim();
        console.log('[CHAT.JS] Form submitted with prompt length:', prompt.length);
        if (!prompt) {
            console.log('[CHAT.JS] Empty prompt, ignoring submission');
            return;
        }
        await sendPromptStream(prompt);
        // promptInput.innerHTML = '';
    };

    function startEdit(msg, idx) {
        if (!msg.message_id) {
            console.error("Message has no message_id:", msg);
            alert("Cannot edit this message - missing message ID");
            return;
        }

        editingMsgId = msg.message_id;
        editingMsgIdx = idx;
        renderMessages();
    }

    function handleInitialRoute() {
        const path = window.location.pathname;
        const match = path.match(/^\/chat\/([a-f0-9\-]+)$/);
        if (match) {
            openConvo(match[1]);
        } else if (conversations.length > 0 && conversations[0].conversation_id) {
            navigateToConvo(conversations[0].conversation_id);
        } else {
            messagesDiv.innerHTML = '<div class="empty-state">No conversations yet.</div>';
            promptForm.style.display = "block";
        }
    }

    window.onpopstate = function (event) {
        const path = window.location.pathname;
        const match = path.match(/^\/chat\/([a-f0-9\-]+)$/);
        if (match) {
            openConvo(match[1]);
        }
    };

    autoLogin();

    // Initialize send button state
    updateSendButtonState();

    // User menu functionality
    function toggleUserMenu() {
        userMenuDropdown.classList.toggle('show');
    }

    function hideUserMenu() {
        userMenuDropdown.classList.remove('show');
    }

    // Event listeners for user menu
    userMenuBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleUserMenu();
    });

    // Hide menu when clicking outside
    document.addEventListener('click', function(e) {
        if (!userMenuBtn.contains(e.target) && !userMenuDropdown.contains(e.target)) {
            hideUserMenu();
        }
    });

    // Hide menu when pressing escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideUserMenu();
        }
    });

    // Settings button functionality (placeholder for now)
    settingsBtn.addEventListener('click', function() {
        console.log('Settings clicked - to be implemented');
        hideUserMenu();
    });

    // Models button functionality
    const modelsBtn = document.getElementById('modelsBtn');
    modelsBtn.addEventListener('click', function() {
        window.location.href = '/models';
        hideUserMenu();
    });

    async function editMessage(messageId, newContent) {
        const editIndex = messages.findIndex(msg => msg.message_id === messageId);
        if (editIndex !== -1) {
            messages[editIndex].content = newContent;
            messages = messages.slice(0, editIndex + 1);
        }
        
        // Reset the stopping flag when starting a new edit stream
        isStoppingStream = false;
        
        tempUserMsg = null;
        tempAssistantMsg = { role: "assistant", content: "" };
        isStreaming = true;
        updateSendButtonState();
        renderMessages();
        currentAbortController = new AbortController();
        try {
            const response = await fetch(`/api/messages/${messageId}/stream`, {
                method: "PUT",
                headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                body: JSON.stringify(newContent),
                signal: currentAbortController.signal
            });
            if (!response.ok) {
                isStreaming = false;
                updateSendButtonState();
                renderMessages();
                return;
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let shouldReload = false;
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                let parts = buffer.split("\n\n");
                buffer = parts.pop();
                for (const part of parts) {
                    if (part.startsWith("data: ")) {
                        const token = part.slice(6);
                        if (token === "[DONE]" || token === "[INTERRUPTED]") break;
                        if (token === "[SAVED]") {
                            console.log("Received [SAVED] signal from backend, reloading conversation");
                            shouldReload = true;
                            break;
                        }
                        if (token === "[CONTINUING_IN_BACKGROUND]") {
                            console.log("Received [CONTINUING_IN_BACKGROUND] signal - response will be completed in background");
                            tempAssistantMsg.content += "\n\n*[Response will be completed in background]*";
                            renderMessages();
                            shouldReload = true;
                            // Start polling for background processing completion
                            startBackgroundProcessingPolling();
                            break;
                        }
                        
                        // Check if this is a title message
                        try {
                            const parsedToken = JSON.parse(token);
                            if (parsedToken.message && parsedToken.message.title) {
                                // This is a title message - update the conversation title
                                console.log("Received title:", parsedToken.message.title);
                                const currentConvoObj = conversations.find(c => c.conversation_id === currentConvo);
                                if (currentConvoObj) {
                                    currentConvoObj.title = parsedToken.message.title;
                                    renderConvos(); // Update the sidebar
                                    
                                    // Save the title to the database
                                    fetch(`/api/conversations/${currentConvo}/save-title`, {
                                        method: "POST",
                                        headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                                        body: JSON.stringify({ title: parsedToken.message.title })
                                    }).then(res => {
                                        if (res.ok) {
                                            console.log("Title saved to database");
                                        } else {
                                            console.error("Failed to save title to database");
                                        }
                                    }).catch(err => {
                                        console.error("Error saving title:", err);
                                    });
                                }
                                continue; // Skip adding this to the assistant message content
                            }
                        } catch (e) {
                            // Not a JSON object, treat as regular token
                        }
                        
                        // Regular token - add to assistant message
                        tempAssistantMsg.content += JSON.parse(token);
                        const streamingContent = document.getElementById('streaming-content');
                        if (streamingContent) {
                            const isAtBottom = messagesDiv.scrollTop + messagesDiv.clientHeight >= messagesDiv.scrollHeight - 10;
                            streamingContent.innerHTML = marked.parse(tempAssistantMsg.content);
                            if (isAtBottom) {
                                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                            }
                        }
                    }
                }
                if (shouldReload) break;
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('Edit stream was aborted by user');
                // Don't add the interruption message here since backend will handle it
            } else {
                console.error('Edit stream error:', error);
            }
        } finally {
            isStreaming = false;
            currentAbortController = null;
            updateSendButtonState();
            if (isStoppingStream) {
                // Don't clear tempAssistantMsg, keep the partial response
            } else {
                tempAssistantMsg = null;
                await openConvo(currentConvo);
            }
            editingMsgId = null;
            editingMsgIdx = null;
        }
    }

    // Function to update send button state
    function updateSendButtonState() {
        if (isStreaming) {
            sendButton.disabled = false; // Keep enabled so stop button is clickable
            sendButton.style.opacity = '1';
            sendButton.style.cursor = 'pointer';
            // Change button to stop button
            sendButton.textContent = '🛑';
            sendButton.title = 'Stop generating';
            sendButton.type = 'button'; // Change to button type to prevent form submission
            sendButton.onclick = stopStream;
            sendButton.classList.add('stopping');
        } else {
            sendButton.disabled = false;
            sendButton.style.opacity = '1';
            sendButton.style.cursor = 'pointer';
            // Change button back to send button
            sendButton.textContent = '⬆️';
            sendButton.title = 'Send message';
            sendButton.type = 'submit'; // Change back to submit type
            sendButton.onclick = null; // Remove onclick to use form submission
            sendButton.classList.remove('stopping');
        }
    }

    // Function to stop the current stream
    function stopStream() {
        console.log('[CHAT.JS] stopStream called');
        if (currentAbortController) {
            console.log('[CHAT.JS] Stopping stream...');
            isStoppingStream = true;
            const currentPrompt = promptInput.innerText;
            console.log('[CHAT.JS] Preserved prompt:', currentPrompt);
            currentAbortController.abort();
            // No setTimeout or reload here; reload will be triggered by [SAVED] event
            promptInput.innerText = currentPrompt;
            console.log('[CHAT.JS] Stream stop initiated');
        } else {
            console.log('[CHAT.JS] No current AbortController found for stopping');
        }
    }

    async function savePartialResponse(response) {
        console.log('[CHAT.JS] savePartialResponse called with content length:', response?.length);
        try {
            console.log('[CHAT.JS] Saving partial response directly to DB');
            const res = await fetch(`/api/conversations/${currentConvo}/partial-response`, {
                method: "POST",
                headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                body: JSON.stringify({ content: response })
            });
            if (res.ok) {
                console.log('[CHAT.JS] Partial response saved successfully');
                // Reload conversation to show the saved response
                await openConvo(currentConvo);
            } else {
                console.log('[CHAT.JS] Failed to save partial response, status:', res.status);
            }
        } catch (error) {
            console.log('[CHAT.JS] Error saving partial response:', error.message);
        }
    }

    // Function to check if background processing is complete
    async function checkBackgroundProcessing() {
        console.log('[CHAT.JS] checkBackgroundProcessing called');
        if (!currentConvo) {
            console.log('[CHAT.JS] No current conversation, returning');
            return;
        }
        
        try {
            console.log('[CHAT.JS] Fetching processing status');
            const response = await fetch(`/api/conversations/${currentConvo}/processing-status`, {
                headers: { Authorization: "Bearer " + accessToken }
            });
            const status = await response.json();
            console.log('[CHAT.JS] Processing status:', status);
            
            if (!status.processing) {
                // Background processing is complete, reload the conversation
                console.log('[CHAT.JS] Background processing complete, reloading conversation');
                clearInterval(backgroundProcessingCheck);
                backgroundProcessingCheck = null;
                await openConvo(currentConvo);
            } else {
                // Background processing is still active, start real-time streaming
                console.log('[CHAT.JS] Background processing still active, starting resume streaming');
                startResumeStreaming();
            }
        } catch (error) {
            console.log('[CHAT.JS] Error checking background processing status:', error.message);
        }
    }

    // Function to start real-time streaming for resumed conversation
    async function startResumeStreaming() {
        console.log('[CHAT.JS] startResumeStreaming called');
        if (!currentConvo) {
            console.log('[CHAT.JS] No current conversation, returning');
            return;
        }
        
        try {
            console.log('[CHAT.JS] Starting resume streaming...');
            
            // First check if the response is already complete
            console.log('[CHAT.JS] Checking if background processing is already complete');
            const statusResponse = await fetch(`/api/conversations/${currentConvo}/processing-status`, {
                headers: { Authorization: "Bearer " + accessToken }
            });
            const status = await statusResponse.json();
            console.log('[CHAT.JS] Initial processing status:', status);
            
            if (!status.processing) {
                console.log('[CHAT.JS] Background processing already completed, reloading conversation');
                clearInterval(backgroundProcessingCheck);
                backgroundProcessingCheck = null;
                await openConvo(currentConvo);
                return;
            }
            
            // Create temporary assistant message to show streaming
            console.log('[CHAT.JS] Creating temporary assistant message for resume streaming');
            tempAssistantMsg = { 
                role: "assistant", 
                content: "*[Resuming response...]*",
                message_id: null 
            };
            renderMessages();
            
            console.log('[CHAT.JS] Sending resume stream request');
            console.log('[CHAT.JS] Current conversation ID:', currentConvo);
            console.log('[CHAT.JS] Access token available:', !!accessToken);
            console.log('[CHAT.JS] Access token length:', accessToken?.length);
            const response = await fetch(`/api/conversations/${currentConvo}/resume-stream`, {
                method: "POST",
                headers: { Authorization: "Bearer " + accessToken }
            });
            
            console.log('[CHAT.JS] Resume stream response status:', response.status);
            if (!response.ok) {
                console.log('[CHAT.JS] Resume stream request failed, status:', response.status);
                const errorText = await response.text();
                console.log('[CHAT.JS] Error response text:', errorText);
                // If resume streaming fails, check if it's because processing is complete
                console.log('[CHAT.JS] Checking if processing completed while trying to resume');
                const finalStatusResponse = await fetch(`/api/conversations/${currentConvo}/processing-status`, {
                    headers: { Authorization: "Bearer " + accessToken }
                });
                const finalStatus = await finalStatusResponse.json();
                console.log('[CHAT.JS] Final processing status:', finalStatus);
                
                if (!finalStatus.processing) {
                    console.log('[CHAT.JS] Background processing completed while trying to resume, reloading conversation');
                    clearInterval(backgroundProcessingCheck);
                    backgroundProcessingCheck = null;
                    await openConvo(currentConvo);
                    return;
                }
                
                // If we get a 400 error and processing is still active, it might be a race condition
                if (response.status === 400) {
                    console.log('[CHAT.JS] Resume-stream returned 400 - checking if this is a race condition');
                    // Wait a moment and check again
                    console.log('[CHAT.JS] Waiting 1 second before retry');
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    const retryStatusResponse = await fetch(`/api/conversations/${currentConvo}/processing-status`, {
                        headers: { Authorization: "Bearer " + accessToken }
                    });
                    const retryStatus = await retryStatusResponse.json();
                    console.log('[CHAT.JS] Retry processing status:', retryStatus);
                    
                    if (!retryStatus.processing) {
                        console.log('[CHAT.JS] Background processing completed during retry, reloading conversation');
                        clearInterval(backgroundProcessingCheck);
                        backgroundProcessingCheck = null;
                        await openConvo(currentConvo);
                        return;
                    }
                }
                
                return;
            }
            
            console.log('[CHAT.JS] Resume streaming connected successfully');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let updateCount = 0;
            console.log('[CHAT.JS] Resume stream reader and decoder initialized');
            
            // Clear the temporary message and start fresh
            tempAssistantMsg.content = "";
            console.log('[CHAT.JS] Cleared temporary assistant message content');
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    console.log('[CHAT.JS] Resume streaming ended');
                    break;
                }
                
                buffer += decoder.decode(value, { stream: true });
                let parts = buffer.split("\n\n");
                buffer = parts.pop();
                console.log('[CHAT.JS] Resume stream processing parts, count:', parts.length);
                
                for (const part of parts) {
                    if (part.startsWith("data: ")) {
                        const token = part.slice(6);
                        if (token === "[DONE]") {
                            console.log('[CHAT.JS] Resume streaming completed');
                            clearInterval(backgroundProcessingCheck);
                            backgroundProcessingCheck = null;
                            resumeStreamingCompleted = true; // Mark as completed
                            // Clear temporary messages before reloading conversation
                            tempUserMsg = null;
                            tempAssistantMsg = null;
                            await openConvo(currentConvo);
                            return;
                        }
                        if (token === "[ERROR]") {
                            console.log('[CHAT.JS] Resume streaming error');
                            clearInterval(backgroundProcessingCheck);
                            backgroundProcessingCheck = null;
                            resumeStreamingCompleted = true; // Mark as completed
                            // Clear temporary messages before reloading conversation
                            tempUserMsg = null;
                            tempAssistantMsg = null;
                            await openConvo(currentConvo);
                            return;
                        }
                        
                        // Check if this is a title message
                        try {
                            const parsedToken = JSON.parse(token);
                            if (parsedToken.message && parsedToken.message.title) {
                                // This is a title message - update the conversation title
                                console.log("Received title:", parsedToken.message.title);
                                const currentConvoObj = conversations.find(c => c.conversation_id === currentConvo);
                                if (currentConvoObj) {
                                    currentConvoObj.title = parsedToken.message.title;
                                    renderConvos(); // Update the sidebar
                                    
                                    // Save the title to the database
                                    fetch(`/api/conversations/${currentConvo}/save-title`, {
                                        method: "POST",
                                        headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
                                        body: JSON.stringify({ title: parsedToken.message.title })
                                    }).then(res => {
                                        if (res.ok) {
                                            console.log("Title saved to database");
                                        } else {
                                            console.error("Failed to save title to database");
                                        }
                                    }).catch(err => {
                                        console.error("Error saving title:", err);
                                    });
                                }
                                continue; // Skip adding this to the assistant message content
                            }
                        } catch (e) {
                            // Not a JSON object, treat as regular token
                        }
                        
                        // Regular token - add to assistant message
                        try {
                            const parsedToken = JSON.parse(token);
                            tempAssistantMsg.content += parsedToken;
                            updateCount++;
                            console.log(`Resume streaming update #${updateCount}: +${parsedToken.length} chars`);
                            renderMessages();
                            
                            // Auto-scroll to bottom
                            const isAtBottom = messagesDiv.scrollTop + messagesDiv.clientHeight >= messagesDiv.scrollHeight - 10;
                            if (isAtBottom) {
                                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                            }
                        } catch (e) {
                            // Not a JSON object, treat as regular token
                            tempAssistantMsg.content += token;
                            updateCount++;
                            console.log(`Resume streaming update #${updateCount}: +${token.length} chars`);
                            renderMessages();
                            
                            // Auto-scroll to bottom
                            const isAtBottom = messagesDiv.scrollTop + messagesDiv.clientHeight >= messagesDiv.scrollHeight - 10;
                            if (isAtBottom) {
                                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                            }
                        }
                    }
                }
            }
        } catch (error) {
            console.error("Error in resume streaming:", error);
            // If there's an error, check if processing is complete and reload
            try {
                const errorStatusResponse = await fetch(`/api/conversations/${currentConvo}/processing-status`, {
                    headers: { Authorization: "Bearer " + accessToken }
                });
                const errorStatus = await errorStatusResponse.json();
                
                if (!errorStatus.processing) {
                    console.log("Background processing completed after error, reloading conversation");
                    clearInterval(backgroundProcessingCheck);
                    backgroundProcessingCheck = null;
                    await openConvo(currentConvo);
                }
            } catch (statusError) {
                console.error("Error checking status after resume error:", statusError);
            }
        }
    }

    // Function to start polling for background processing completion
    function startBackgroundProcessingPolling() {
        console.log('[CHAT.JS] startBackgroundProcessingPolling called');
        if (backgroundProcessingCheck) {
            console.log('[CHAT.JS] Clearing existing background processing check interval');
            clearInterval(backgroundProcessingCheck);
        }
        // Start real-time streaming immediately instead of polling
        console.log('[CHAT.JS] Starting resume streaming immediately');
        startResumeStreaming();
        // Keep a minimal fallback polling mechanism just in case
        backgroundProcessingCheck = setInterval(checkBackgroundProcessing, 10000); // Check every 10 seconds as fallback
        console.log('[CHAT.JS] Set up fallback polling interval (10 seconds)');
        showStatus("Resuming response in real-time...", "processing");
    }

    // Function to show status messages
    function showStatus(message, type = "info") {
        console.log('[CHAT.JS] showStatus called:', message, 'type:', type);
        statusEl.textContent = message;
        statusEl.className = `show ${type}`;
        setTimeout(() => {
            statusEl.classList.remove('show');
            console.log('[CHAT.JS] Status message hidden after 5 seconds');
        }, 5000);
    }

    function showModelDetails(modelId) {
        console.log('[CHAT.JS] showModelDetails called for model ID:', modelId);
        // Find the model data from the suggestions
        let model = null;
        for (const category of ['trending', 'used', 'new', 'recommended']) {
            const section = window.modelSuggestions[category];
            if (section) {
                model = section.find(m => m.model_id === modelId);
                if (model) {
                    console.log('[CHAT.JS] Found model in category:', category);
                    break;
                }
            }
        }
        
        if (!model) {
            console.log('[CHAT.JS] Model not found in suggestions');
            return;
        }
        
        const modal = document.createElement('div');
        modal.className = 'modal show';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">${model.name}</h2>
                    <button class="close-btn" onclick="this.closest('.modal').remove()">&times;</button>
                </div>
                <div style="color: #e4e4e7; white-space: pre-line; margin-bottom: 1rem;">
                    ${model.short_description || 'No short description'}
                </div>
                <div style="color: #a1a1aa; white-space: pre-line;">
                    ${model.long_description || 'No detailed description available'}
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
        console.log('[CHAT.JS] Model details modal created and displayed');
    }

    // Initialize the application
    console.log('[CHAT.JS] Starting application initialization');
    autoLogin();
    console.log('[CHAT.JS] Application initialization completed');
});