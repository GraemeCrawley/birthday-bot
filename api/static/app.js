// Service Worker and Push Notification Support
let swRegistration = null;
let pushSubscription = null;

async function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) {
        console.log('Service workers not supported');
        return null;
    }

    try {
        const registration = await navigator.serviceWorker.register('/service-worker.js');
        console.log('Service worker registered');
        swRegistration = registration;
        return registration;
    } catch (e) {
        console.error('Service worker registration failed:', e);
        return null;
    }
}

async function getVapidPublicKey() {
    try {
        const response = await fetch('/api/push/vapid-public-key');
        if (!response.ok) return null;
        const data = await response.json();
        return data.publicKey;
    } catch (e) {
        console.error('Failed to get VAPID key:', e);
        return null;
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

async function subscribeToPush() {
    console.log('subscribeToPush called');

    if (!('serviceWorker' in navigator)) {
        alert('Service workers are not supported in this browser');
        return false;
    }

    if (!('PushManager' in window)) {
        alert('Push notifications are not supported in this browser');
        return false;
    }

    if (!swRegistration) {
        console.log('No SW registration, registering now...');
        await registerServiceWorker();
    }

    if (!swRegistration) {
        alert('Service worker not available');
        return false;
    }

    console.log('Requesting notification permission...');
    const permission = await Notification.requestPermission();
    console.log('Permission result:', permission);
    if (permission !== 'granted') {
        alert('Notification permission denied. Please allow notifications in your browser settings.');
        return false;
    }

    const vapidPublicKey = await getVapidPublicKey();
    if (!vapidPublicKey) {
        alert('Push notifications not configured on server');
        return false;
    }

    try {
        console.log('Subscribing to push manager...');
        pushSubscription = await swRegistration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
        });
        console.log('Push subscription created:', pushSubscription);

        const subscriptionJson = pushSubscription.toJSON();
        await API.post('/api/push/subscribe', {
            endpoint: subscriptionJson.endpoint,
            keys: {
                p256dh: subscriptionJson.keys.p256dh,
                auth: subscriptionJson.keys.auth
            }
        });

        updatePushButton(true);
        alert('Push notifications enabled!');
        return true;
    } catch (e) {
        console.error('Push subscription failed:', e);
        alert('Failed to subscribe to push notifications: ' + e.message);
        return false;
    }
}

async function unsubscribeFromPush() {
    if (!pushSubscription) {
        return true;
    }

    try {
        const subscriptionJson = pushSubscription.toJSON();
        await API.post('/api/push/unsubscribe', {
            endpoint: subscriptionJson.endpoint,
            keys: {
                p256dh: subscriptionJson.keys.p256dh,
                auth: subscriptionJson.keys.auth
            }
        });

        await pushSubscription.unsubscribe();
        pushSubscription = null;
        updatePushButton(false);
        return true;
    } catch (e) {
        console.error('Push unsubscribe failed:', e);
        return false;
    }
}

function updatePushButton(subscribed) {
    const btn = document.getElementById('push-toggle-btn');
    if (btn) {
        btn.textContent = subscribed ? 'Disable Push Notifications' : 'Enable Push Notifications';
        btn.classList.toggle('subscribed', subscribed);
    }
}

async function checkPushSubscription() {
    if (!swRegistration) return;

    try {
        pushSubscription = await swRegistration.pushManager.getSubscription();
        updatePushButton(!!pushSubscription);
    } catch (e) {
        console.error('Failed to check push subscription:', e);
    }
}

async function testPushNotification() {
    try {
        const result = await API.post('/api/push/test');
        if (result.success) {
            alert('Test notification sent! You should receive it shortly.');
        } else {
            alert('Failed to send test notification');
        }
    } catch (e) {
        console.error('Test push failed:', e);
        alert('Failed to send test notification');
    }
}

const API = {
    async get(url) {
        const res = await fetch(url);
        return res.json();
    },
    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return res.json();
    },
    async put(url, data) {
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return res.json();
    },
    async delete(url) {
        const res = await fetch(url, { method: 'DELETE' });
        return res.json();
    }
};

let allPeople = [];
let currentPersonId = null;

function showView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    document.getElementById(`${viewName}-view`).classList.remove('hidden');
    document.querySelector(`[data-view="${viewName}"]`).classList.add('active');

    if (viewName === 'dashboard') loadDashboard();
    if (viewName === 'people') loadPeople();
    if (viewName === 'settings') loadSettings();
}

function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

function getCountdownClass(days) {
    if (days <= 7) return 'urgent';
    if (days <= 14) return 'soon';
    return 'normal';
}

function formatDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDays(days) {
    if (days === 0) return 'Today!';
    if (days === 1) return '1 day';
    return `${days} days`;
}

async function loadDashboard() {
    try {
        const data = await API.get('/api/dashboard');
        allPeople = data;
        const list = document.getElementById('dashboard-list');

        if (data.length === 0) {
            list.innerHTML = '<tr><td colspan="4" class="empty-state">No birthdays yet. Add some people!</td></tr>';
            return;
        }

        list.innerHTML = data.map(person => `
            <tr class="clickable" onclick="showPersonGifts(${person.id})">
                <td>${escapeHtml(person.name)}</td>
                <td>${formatDate(person.birthday)}</td>
                <td>${person.age_turning}</td>
                <td class="days-cell ${getCountdownClass(person.days_until)}">${formatDays(person.days_until)}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load dashboard:', e);
    }
}

async function loadPeople() {
    try {
        const data = await API.get('/api/people');
        allPeople = data;
        const list = document.getElementById('people-list');

        if (data.length === 0) {
            list.innerHTML = '<tr><td colspan="5" class="empty-state">No people added yet.</td></tr>';
            return;
        }

        list.innerHTML = data.map(person => `
            <tr data-person-id="${person.id}">
                <td>${escapeHtml(person.name)}</td>
                <td>${formatDate(person.birthday)}</td>
                <td>${escapeHtml(person.notes || '-')}</td>
                <td><span class="gift-count clickable" onclick="showPersonGifts(${person.id})">${person.gifts.length} gifts</span></td>
                <td>
                    <div class="table-actions">
                        <button class="edit-btn" onclick="editPerson(${person.id})">Edit</button>
                        <button class="delete-btn" onclick="deletePerson(${person.id})">Delete</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load people:', e);
    }
}

async function loadSettings() {
    try {
        const data = await API.get('/api/settings');
        document.getElementById('notification-email').value = data.notification_email || '';
        document.getElementById('notify-thresholds').value = data.notify_thresholds || '60,30,7,0';

        // Check push subscription status
        await checkPushSubscription();
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
}

function openPersonModal(person = null) {
    const modal = document.getElementById('person-modal');
    const title = document.getElementById('person-modal-title');

    if (person) {
        title.textContent = 'Edit Person';
        document.getElementById('person-id').value = person.id;
        document.getElementById('person-name').value = person.name;
        document.getElementById('person-birthday').value = person.birthday;
        document.getElementById('person-notes').value = person.notes || '';
    } else {
        title.textContent = 'Add Person';
        document.getElementById('person-form').reset();
        document.getElementById('person-id').value = '';
    }

    modal.classList.remove('hidden');
}

async function editPerson(id) {
    try {
        const person = await API.get(`/api/people/${id}`);
        openPersonModal(person);
    } catch (e) {
        console.error('Failed to load person:', e);
    }
}

async function deletePerson(id) {
    if (!confirm('Are you sure you want to delete this person and all their gift ideas?')) return;

    try {
        await API.delete(`/api/people/${id}`);
        loadPeople();
    } catch (e) {
        console.error('Failed to delete person:', e);
    }
}

async function openGiftModal(preselectedPersonId = null) {
    document.getElementById('gift-form').reset();

    // Populate the person dropdown
    const select = document.getElementById('gift-person-select');
    const search = document.getElementById('gift-person-search');

    // Load people if not already loaded
    if (allPeople.length === 0) {
        allPeople = await API.get('/api/people');
    }

    // Sort by name
    const sortedPeople = [...allPeople].sort((a, b) => a.name.localeCompare(b.name));

    select.innerHTML = '<option value="">Select a person...</option>' +
        sortedPeople.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');

    search.value = '';

    // Pre-select person if provided
    if (preselectedPersonId) {
        select.value = preselectedPersonId;
    }

    document.getElementById('gift-modal').classList.remove('hidden');
}

async function openGiftModalForPerson(personId) {
    await openGiftModal(personId);
}

function filterPersonDropdown() {
    const search = document.getElementById('gift-person-search').value.toLowerCase();
    const select = document.getElementById('gift-person-select');

    const sortedPeople = [...allPeople].sort((a, b) => a.name.localeCompare(b.name));
    const filtered = search ? sortedPeople.filter(p => p.name.toLowerCase().includes(search)) : sortedPeople;

    select.innerHTML = '<option value="">Select a person...</option>' +
        filtered.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');

    // Auto-select if only one match
    if (filtered.length === 1) {
        select.value = filtered[0].id;
    }
}

async function showPersonGifts(personId) {
    currentPersonId = personId;
    const person = allPeople.find(p => p.id === personId);
    if (!person) return;

    document.getElementById('person-gifts-title').textContent = `Gifts for ${person.name}`;

    const list = document.getElementById('person-gifts-list');
    if (person.gifts.length === 0) {
        list.innerHTML = '<div class="empty-gifts">No gift ideas yet. Add one!</div>';
    } else {
        list.innerHTML = person.gifts.map(g => `
            <div class="gift-item ${g.purchased ? 'purchased' : ''}">
                <input type="checkbox" class="gift-checkbox"
                    ${g.purchased ? 'checked' : ''}
                    onchange="toggleGiftInModal(${g.id}, this.checked)">
                <div class="gift-info">
                    <div class="gift-name">${escapeHtml(g.idea)}</div>
                    <div class="gift-meta">
                        ${g.price ? `$${g.price}` : ''}
                        ${g.price && g.url ? ' · ' : ''}
                        ${g.url ? `<a href="${escapeHtml(g.url)}" target="_blank" class="gift-link">View link</a>` : ''}
                    </div>
                </div>
                <button class="gift-delete" onclick="deleteGiftInModal(${g.id})">Delete</button>
            </div>
        `).join('');
    }

    document.getElementById('person-gifts-modal').classList.remove('hidden');
}

async function toggleGiftInModal(id, purchased) {
    try {
        await API.put(`/api/gifts/${id}`, { purchased });
        // Refresh data and modal
        allPeople = await API.get('/api/dashboard');
        if (currentPersonId) {
            showPersonGifts(currentPersonId);
        }
    } catch (e) {
        console.error('Failed to toggle gift:', e);
    }
}

async function deleteGiftInModal(id) {
    if (!confirm('Delete this gift idea?')) return;

    try {
        await API.delete(`/api/gifts/${id}`);
        // Refresh data and modal
        allPeople = await API.get('/api/dashboard');
        if (currentPersonId) {
            showPersonGifts(currentPersonId);
        }
    } catch (e) {
        console.error('Failed to delete gift:', e);
    }
}

async function toggleGift(id, purchased) {
    try {
        await API.put(`/api/gifts/${id}`, { purchased });
        loadPeople();
    } catch (e) {
        console.error('Failed to toggle gift:', e);
    }
}

async function deleteGift(id) {
    if (!confirm('Delete this gift idea?')) return;

    try {
        await API.delete(`/api/gifts/${id}`);
        loadPeople();
    } catch (e) {
        console.error('Failed to delete gift:', e);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Event Listeners
document.addEventListener('DOMContentLoaded', async () => {
    // Register service worker
    await registerServiceWorker();

    // Load dashboard directly
    loadDashboard();
    await checkPushSubscription();
});

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => showView(btn.dataset.view));
});

document.getElementById('add-person-btn').addEventListener('click', () => openPersonModal());

document.getElementById('add-gift-btn').addEventListener('click', () => openGiftModal());

document.getElementById('gift-person-search').addEventListener('input', filterPersonDropdown);

document.getElementById('add-gift-for-person-btn').addEventListener('click', () => {
    if (currentPersonId) {
        closeModal('person-gifts-modal');
        openGiftModalForPerson(currentPersonId);
    }
});

document.getElementById('person-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const id = document.getElementById('person-id').value;
    const data = {
        name: document.getElementById('person-name').value,
        birthday: document.getElementById('person-birthday').value,
        notes: document.getElementById('person-notes').value || null
    };

    try {
        if (id) {
            await API.put(`/api/people/${id}`, data);
        } else {
            await API.post('/api/people', data);
        }
        closeModal('person-modal');
        loadPeople();
    } catch (e) {
        console.error('Failed to save person:', e);
    }
});

document.getElementById('gift-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const personId = document.getElementById('gift-person-select').value;
    if (!personId) {
        alert('Please select a person');
        return;
    }

    const price = document.getElementById('gift-price').value;
    const data = {
        idea: document.getElementById('gift-idea').value,
        price: price ? parseFloat(price) : null,
        url: document.getElementById('gift-url').value || null
    };

    try {
        await API.post(`/api/people/${personId}/gifts`, data);
        closeModal('gift-modal');
        loadDashboard();
    } catch (e) {
        console.error('Failed to save gift:', e);
    }
});

document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = {
        notification_email: document.getElementById('notification-email').value || null,
        notify_thresholds: document.getElementById('notify-thresholds').value.trim() || '60,30,7,0'
    };

    try {
        await API.put('/api/settings', data);
        alert('Settings saved!');
    } catch (e) {
        console.error('Failed to save settings:', e);
        alert('Failed to save settings');
    }
});

// Close modals on outside click
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });
});

// Push notification controls
const pushToggleBtn = document.getElementById('push-toggle-btn');
const pushTestBtn = document.getElementById('push-test-btn');

if (pushToggleBtn) {
    pushToggleBtn.addEventListener('click', async () => {
        console.log('Push toggle clicked, current subscription:', pushSubscription);
        if (pushSubscription) {
            await unsubscribeFromPush();
        } else {
            await subscribeToPush();
        }
    });
} else {
    console.warn('push-toggle-btn not found');
}

if (pushTestBtn) {
    pushTestBtn.addEventListener('click', testPushNotification);
} else {
    console.warn('push-test-btn not found');
}
