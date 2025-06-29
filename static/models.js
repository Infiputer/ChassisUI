// Models page JavaScript
let currentModelId = null;
let models = [];
let accessToken = null;

// DOM elements
const modelsGrid = document.getElementById('modelsGrid');
const addModelBtn = document.getElementById('addModelBtn');
const modelModal = document.getElementById('modelModal');
const deleteModal = document.getElementById('deleteModal');
const modelForm = document.getElementById('modelForm');
const modalTitle = document.getElementById('modalTitle');
const closeModal = document.getElementById('closeModal');
const closeDeleteModalBtn = document.getElementById('closeDeleteModal');
const cancelBtn = document.getElementById('cancelBtn');
const saveBtn = document.getElementById('saveBtn');
const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
const addEndpointBtn = document.getElementById('addEndpointBtn');
const endpointsList = document.getElementById('endpointsList');
const userMenuBtn = document.getElementById('userMenuBtn');
const userMenuDropdown = document.getElementById('userMenuDropdown');
const logoutBtn = document.getElementById('logoutBtn');

// Initialize the page
document.addEventListener('DOMContentLoaded', function() {
    autoLogin();
});

// Authentication function
async function autoLogin() {
    try {
        const res = await fetch("/auto-login");
        if (!res.ok) throw new Error("Not logged in");
        const data = await res.json();
        accessToken = data.access_token;
        loadModels();
        setupEventListeners();
    } catch {
        window.location = "/";
    }
}

function setupEventListeners() {
    // Modal controls
    addModelBtn.addEventListener('click', () => openModelModal());
    closeModal.addEventListener('click', closeModelModal);
    cancelBtn.addEventListener('click', closeModelModal);
    modelForm.addEventListener('submit', handleModelSubmit);
    
    // Delete modal controls
    closeDeleteModalBtn.addEventListener('click', closeDeleteModal);
    cancelDeleteBtn.addEventListener('click', closeDeleteModal);
    confirmDeleteBtn.addEventListener('click', handleModelDelete);
    
    // Endpoint controls
    addEndpointBtn.addEventListener('click', addEndpointForm);
    
    // User menu
    userMenuBtn.addEventListener('click', toggleUserMenu);
    logoutBtn.addEventListener('click', handleLogout);
    
    // Close modals when clicking outside
    window.addEventListener('click', (e) => {
        if (e.target === modelModal) closeModelModal();
        if (e.target === deleteModal) closeDeleteModal();
    });
}

async function loadModels() {
    try {
        const response = await fetch('/api/models', {
            headers: { Authorization: "Bearer " + accessToken }
        });
        if (response.ok) {
            models = await response.json();
            renderModels();
        } else {
            showStatus('Failed to load models', 'error');
        }
    } catch (error) {
        console.error('Error loading models:', error);
        showStatus('Failed to load models', 'error');
    }
}

function renderModels() {
    modelsGrid.innerHTML = '';
    
    if (models.length === 0) {
        modelsGrid.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; color: #a1a1aa; padding: 2rem;">
                <p>No models found. Create your first model to get started.</p>
            </div>
        `;
        return;
    }
    
    models.forEach(model => {
        const modelCard = createModelCard(model);
        modelsGrid.appendChild(modelCard);
    });
}

function createModelCard(model) {
    const card = document.createElement('div');
    card.className = 'model-card';
    const endpoints = model.endpoints || [];
    const activeEndpoints = endpoints.filter(ep => ep.is_active);
    card.innerHTML = `
        <div class="model-header">
            <div>
                <div class="model-name">${escapeHtml(model.name)}</div>
                <div class="model-description">${escapeHtml(model.short_description || 'No description')}</div>
                <button class="action-btn see-more" onclick="showLongDescription('${model.model_id}')">See more</button>
            </div>
            <div class="model-actions">
                <button class="action-btn edit" onclick="editModel('${model.model_id}')">Edit</button>
                <button class="action-btn delete" onclick="deleteModel('${model.model_id}')">Delete</button>
            </div>
        </div>
        <div class="endpoints-section">
            <div class="endpoints-title">Endpoints (${activeEndpoints.length}/${endpoints.length})</div>
            ${endpoints.map(endpoint => `
                <div class="endpoint-item">
                    <div class="endpoint-info">
                        <div class="endpoint-url">${escapeHtml(endpoint.url)}</div>
                        <div class="endpoint-weight">Weight: ${endpoint.weight}</div>
                    </div>
                    <div class="endpoint-status">
                        <div class="status-indicator ${endpoint.is_active ? '' : 'inactive'}"></div>
                        <span style="color: #a1a1aa; font-size: 0.8rem;">
                            ${endpoint.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </div>
                </div>
            `).join('')}
            ${endpoints.length === 0 ? '<p style="color: #a1a1aa; font-size: 0.9rem;">No endpoints configured</p>' : ''}
        </div>
    `;
    return card;
}

function openModelModal(modelId = null) {
    currentModelId = modelId;
    if (modelId) {
        // Edit mode
        const model = models.find(m => m.model_id === modelId);
        if (model) {
            modalTitle.textContent = 'Edit Model';
            document.getElementById('modelName').value = model.name;
            document.getElementById('modelShortDescription').value = model.short_description || '';
            document.getElementById('modelLongDescription').value = model.long_description || '';
            // Load endpoints
            endpointsList.innerHTML = '';
            if (model.endpoints && model.endpoints.length > 0) {
                model.endpoints.forEach(endpoint => {
                    addEndpointForm(endpoint);
                });
            } else {
                addEndpointForm();
            }
        }
    } else {
        // Add mode
        modalTitle.textContent = 'Add Model';
        modelForm.reset();
        endpointsList.innerHTML = '';
        addEndpointForm();
    }
    modelModal.classList.add('show');
}

function closeModelModal() {
    modelModal.classList.remove('show');
    currentModelId = null;
    modelForm.reset();
    endpointsList.innerHTML = '';
}

function addEndpointForm(endpoint = null) {
    const endpointForm = document.createElement('div');
    endpointForm.className = 'endpoint-form';
    
    const isActive = endpoint ? endpoint.is_active : true;
    const weight = endpoint ? endpoint.weight : 1;
    
    endpointForm.innerHTML = `
        <div class="endpoint-form-row">
            <div class="endpoint-form-group">
                <label class="form-label">Endpoint URL</label>
                <input type="url" class="form-input endpoint-url" value="${endpoint ? escapeHtml(endpoint.url) : ''}" required>
            </div>
        </div>
        <div class="endpoint-form-row">
            <div class="endpoint-form-group">
                <label class="form-label">Active</label>
                <select class="form-input endpoint-active">
                    <option value="true" ${isActive ? 'selected' : ''}>Active</option>
                    <option value="false" ${!isActive ? 'selected' : ''}>Inactive</option>
                </select>
            </div>
            <div class="endpoint-form-group weight">
                <label class="form-label">Weight</label>
                <input type="number" class="form-input endpoint-weight" value="${weight}" min="1" max="10" required>
            </div>
            <div class="endpoint-form-group" style="flex: 0 0 auto; align-self: end;">
                <button type="button" class="remove-endpoint-btn" onclick="removeEndpointForm(this)">Remove</button>
            </div>
        </div>
    `;
    
    endpointsList.appendChild(endpointForm);
}

function removeEndpointForm(button) {
    const endpointForm = button.closest('.endpoint-form');
    endpointForm.remove();
    
    // Ensure at least one endpoint form exists
    if (endpointsList.children.length === 0) {
        addEndpointForm();
    }
}

async function handleModelSubmit(e) {
    e.preventDefault();
    const formData = {
        name: document.getElementById('modelName').value.trim(),
        short_description: document.getElementById('modelShortDescription').value.trim(),
        long_description: document.getElementById('modelLongDescription').value.trim(),
        endpoints: []
    };
    
    // Collect endpoint data
    const endpointForms = endpointsList.querySelectorAll('.endpoint-form');
    endpointForms.forEach(form => {
        const url = form.querySelector('.endpoint-url').value.trim();
        const isActive = form.querySelector('.endpoint-active').value === 'true';
        const weight = parseInt(form.querySelector('.endpoint-weight').value);
        
        if (url) {
            formData.endpoints.push({
                url: url,
                is_active: isActive,
                weight: weight
            });
        }
    });
    
    if (formData.endpoints.length === 0) {
        showStatus('At least one endpoint is required', 'error');
        return;
    }
    
    try {
        const url = currentModelId ? `/api/models/${currentModelId}` : '/api/models';
        const method = currentModelId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + accessToken
            },
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            showStatus(currentModelId ? 'Model updated successfully' : 'Model created successfully', 'success');
            closeModelModal();
            loadModels();
        } else {
            const error = await response.text();
            showStatus(`Failed to save model: ${error}`, 'error');
        }
    } catch (error) {
        console.error('Error saving model:', error);
        showStatus('Failed to save model', 'error');
    }
}

function deleteModel(modelId) {
    currentModelId = modelId;
    deleteModal.classList.add('show');
}

function closeDeleteModal() {
    deleteModal.classList.remove('show');
    currentModelId = null;
}

async function handleModelDelete() {
    if (!currentModelId) return;
    
    try {
        const response = await fetch(`/api/models/${currentModelId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': 'Bearer ' + accessToken
            }
        });
        
        if (response.ok) {
            showStatus('Model deleted successfully', 'success');
            closeDeleteModal();
            loadModels();
        } else {
            const error = await response.text();
            showStatus(`Failed to delete model: ${error}`, 'error');
        }
    } catch (error) {
        console.error('Error deleting model:', error);
        showStatus('Failed to delete model', 'error');
    }
}

function editModel(modelId) {
    openModelModal(modelId);
}

function toggleUserMenu() {
    userMenuDropdown.classList.toggle('show');
}

async function handleLogout() {
    // Logout and redirect to home page
    await fetch("/logout", { method: "POST" });
    window.location = "/";
}

function showStatus(message, type = 'info') {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = `show ${type}`;
    
    setTimeout(() => {
        status.classList.remove('show');
    }, 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Close user menu when clicking outside
document.addEventListener('click', (e) => {
    if (!userMenuBtn.contains(e.target) && !userMenuDropdown.contains(e.target)) {
        userMenuDropdown.classList.remove('show');
    }
});

// Add a modal for long description
function showLongDescription(modelId) {
    const model = models.find(m => m.model_id === modelId);
    if (!model) return;
    const modal = document.createElement('div');
    modal.className = 'modal show';
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title">${escapeHtml(model.name)}</h2>
          <button class="close-btn" onclick="this.closest('.modal').remove()">&times;</button>
        </div>
        <div style="color: #e4e4e7; white-space: pre-line;">${escapeHtml(model.long_description || 'No details')}</div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
} 