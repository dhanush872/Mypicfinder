// EventFrame Photographer Studio Controller
(() => {
  let authToken = localStorage.getItem('ef_photographer_token');
  let currentUser = null;
  let activeEvent = null;
  let isRegisterMode = false;

  // DOM Elements
  const authSection = document.getElementById('authSection');
  const authForm = document.getElementById('authForm');
  const authHeading = document.getElementById('authHeading');
  const fullNameGroup = document.getElementById('fullNameGroup');
  const fullNameInput = document.getElementById('fullNameInput');
  const emailInput = document.getElementById('emailInput');
  const passwordInput = document.getElementById('passwordInput');
  const authSubmitBtn = document.getElementById('authSubmitBtn');
  const toggleAuthModeBtn = document.getElementById('toggleAuthModeBtn');
  const authError = document.getElementById('authError');

  const dashboardSection = document.getElementById('dashboardSection');
  const userProfileBadge = document.getElementById('userProfileBadge');
  const userEmailText = document.getElementById('userEmailText');
  const logoutBtn = document.getElementById('logoutBtn');

  const eventsView = document.getElementById('eventsView');
  const eventsGrid = document.getElementById('eventsGrid');
  const newEventBtn = document.getElementById('newEventBtn');

  const eventDetailView = document.getElementById('eventDetailView');
  const backToEventsBtn = document.getElementById('backToEventsBtn');
  const detailTitle = document.getElementById('detailTitle');
  const detailVenueDate = document.getElementById('detailVenueDate');
  const showQrBtn = document.getElementById('showQrBtn');
  const editSettingsBtn = document.getElementById('editSettingsBtn');
  const deleteEventBtn = document.getElementById('deleteEventBtn');

  const watcherStatusBadge = document.getElementById('watcherStatusBadge');
  const watcherFolderText = document.getElementById('watcherFolderText');
  const watcherStatsText = document.getElementById('watcherStatsText');
  const toggleWatcherBtn = document.getElementById('toggleWatcherBtn');
  const viewAuditLogsBtn = document.getElementById('viewAuditLogsBtn');

  const photoDropZone = document.getElementById('photoDropZone');
  const bulkFileInput = document.getElementById('bulkFileInput');
  const browseFilesBtn = document.getElementById('browseFilesBtn');
  const uploadProgress = document.getElementById('uploadProgress');

  const photosGrid = document.getElementById('photosGrid');
  const photoCountSpan = document.getElementById('photoCountSpan');
  const faceCountSpan = document.getElementById('faceCountSpan');

  // Modals
  const eventModal = document.getElementById('eventModal');
  const eventModalTitle = document.getElementById('eventModalTitle');
  const eventForm = document.getElementById('eventForm');
  const eventTitleInput = document.getElementById('eventTitleInput');
  const eventVenueInput = document.getElementById('eventVenueInput');
  const eventDateInput = document.getElementById('eventDateInput');
  const eventPinInput = document.getElementById('eventPinInput');
  const strictSelfieModeInput = document.getElementById('strictSelfieModeInput');
  const watchedFolderInput = document.getElementById('watchedFolderInput');
  const cancelEventModalBtn = document.getElementById('cancelEventModalBtn');

  const qrModal = document.getElementById('qrModal');
  const qrImage = document.getElementById('qrImage');
  const guestShareUrlInput = document.getElementById('guestShareUrlInput');
  const copyShareUrlBtn = document.getElementById('copyShareUrlBtn');
  const downloadQrPngBtn = document.getElementById('downloadQrPngBtn');
  const downloadQrSvgBtn = document.getElementById('downloadQrSvgBtn');
  const revokeTokenBtn = document.getElementById('revokeTokenBtn');
  const closeQrModalBtn = document.getElementById('closeQrModalBtn');

  const auditModal = document.getElementById('auditModal');
  const auditLogsContainer = document.getElementById('auditLogsContainer');
  const closeAuditModalBtn = document.getElementById('closeAuditModalBtn');

  // --- API Fetch Helper ---
  async function apiFetch(endpoint, options = {}) {
    const headers = options.headers || {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const resp = await fetch(endpoint, { credentials: 'same-origin', ...options, headers });
    if (resp.status === 401) {
      handleLogout();
      throw new Error('Session expired. Please sign in again.');
    }
    return resp;
  }

  function extractErrorMessage(errJson, defaultMsg) {
    if (!errJson) return defaultMsg;
    if (typeof errJson.detail === 'string') return errJson.detail;
    if (Array.isArray(errJson.detail) && errJson.detail.length > 0) {
      return errJson.detail.map(item => {
        const field = item.loc ? item.loc[item.loc.length - 1] : '';
        return field ? `${field}: ${item.msg}` : item.msg;
      }).join(', ');
    }
    return errJson.message || defaultMsg;
  }

  // --- Auth Handlers ---
  toggleAuthModeBtn.addEventListener('click', () => {
    isRegisterMode = !isRegisterMode;
    authHeading.textContent = isRegisterMode ? 'Create Photographer Account' : 'Photographer Sign In';
    authSubmitBtn.textContent = isRegisterMode ? 'Register Account' : 'Sign In';
    toggleAuthModeBtn.textContent = isRegisterMode ? 'Already have an account? Sign in' : 'Need an account? Register here';
    fullNameGroup.classList.toggle('d-none', !isRegisterMode);
    authError.style.display = 'none';
  });

  authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    authError.style.display = 'none';
    const email = emailInput.value.trim().toLowerCase();
    const password = passwordInput.value;
    const fullName = fullNameInput.value.trim();

    try {
      if (isRegisterMode) {
        // Register
        const regResp = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, full_name: fullName || 'Photographer' })
        });
        if (!regResp.ok) {
          const err = await regResp.json().catch(() => ({}));
          throw new Error(extractErrorMessage(err, 'Registration failed. Check your inputs.'));
        }
      }

      // Login
      const loginResp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!loginResp.ok) {
        const err = await loginResp.json().catch(() => ({}));
        throw new Error(extractErrorMessage(err, 'Invalid email or password'));
      }

      const data = await loginResp.json();
      authToken = data.access_token;
      currentUser = data.user;
      localStorage.setItem('ef_photographer_token', authToken);
      showDashboard();
    } catch (err) {
      authError.textContent = err.message;
      authError.style.display = 'block';
    }
  });

  logoutBtn.addEventListener('click', handleLogout);

  function handleLogout() {
    authToken = null;
    currentUser = null;
    activeEvent = null;
    localStorage.removeItem('ef_photographer_token');
    authSection.classList.remove('d-none');
    dashboardSection.classList.add('d-none');
    userProfileBadge.classList.add('d-none');
  }

  async function checkSession() {
    if (!authToken) {
      handleLogout();
      return;
    }
    try {
      const resp = await apiFetch('/api/auth/me');
      if (!resp.ok) throw new Error();
      currentUser = await resp.json();
      showDashboard();
    } catch {
      handleLogout();
    }
  }

  function showDashboard() {
    authSection.classList.add('d-none');
    dashboardSection.classList.remove('d-none');
    userProfileBadge.classList.remove('d-none');
    userEmailText.textContent = currentUser.email;
    loadEvents();
  }

  // --- Events Management ---
  async function loadEvents() {
    eventsView.classList.remove('d-none');
    eventDetailView.classList.add('d-none');
    eventsGrid.innerHTML = '<div style="color: var(--text-muted);">Loading events...</div>';

    try {
      const resp = await apiFetch('/api/events');
      if (!resp.ok) throw new Error('Failed to load events');
      const events = await resp.json();

      if (events.length === 0) {
        eventsGrid.innerHTML = `
          <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
            <h3>No events created yet</h3>
            <p style="margin-top: 0.5rem;">Click "+ New Event" above to create your first session.</p>
          </div>
        `;
        return;
      }

      eventsGrid.innerHTML = '';
      events.forEach((ev) => {
        const card = document.createElement('div');
        card.className = 'card';
        card.style.cursor = 'pointer';

        const dtStr = ev.event_date ? new Date(ev.event_date).toLocaleDateString() : '';
        const statusBadge = ev.is_active ? '<span class="badge badge-success">Live</span>' : '<span class="badge badge-warning">Inactive</span>';
        const tetherBadge = ev.watched_folder_active ? '<span class="badge badge-primary">Tether Active</span>' : '';
        const pinBadge = ev.pin_code ? '<span class="badge badge-warning">PIN: ' + ev.pin_code + '</span>' : '';
        const selfieBadge = ev.strict_selfie_mode ? '<span class="badge badge-danger">Strict Selfie Only</span>' : '';

        card.innerHTML = `
          <div class="card-header" style="margin-bottom: 0.75rem;">
            <h3 style="font-size: 1.15rem;">${ev.title}</h3>
            <div style="display: flex; gap: 0.25rem;">${statusBadge}</div>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.75rem;">
            <div>📍 ${ev.venue || 'No venue set'}</div>
            <div>📅 ${dtStr}</div>
          </div>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
            ${pinBadge}
            ${selfieBadge}
            ${tetherBadge}
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-color); padding-top: 0.75rem; font-size: 0.85rem;">
            <span>📸 <strong>${ev.photo_count}</strong> photos</span>
            <span>👤 <strong>${ev.face_count}</strong> faces</span>
          </div>
        `;

        card.addEventListener('click', () => openEventDetail(ev));
        eventsGrid.appendChild(card);
      });
    } catch (err) {
      eventsGrid.innerHTML = `<div class="text-danger">${err.message}</div>`;
    }
  }

  // --- Event Detail View ---
  async function openEventDetail(ev) {
    activeEvent = ev;
    eventsView.classList.add('d-none');
    eventDetailView.classList.remove('d-none');

    detailTitle.textContent = ev.title;
    const dt = ev.event_date ? new Date(ev.event_date).toLocaleDateString() : '';
    detailVenueDate.textContent = `${ev.venue || 'Venue TBD'} • ${dt}`;

    updateWatcherUI();
    loadEventPhotos();
  }

  backToEventsBtn.addEventListener('click', () => {
    loadEvents();
  });

  async function updateWatcherUI() {
    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}/watcher-status`);
      if (resp.ok) {
        const status = await resp.json();
        if (status.is_active) {
          watcherStatusBadge.className = 'badge badge-success';
          watcherStatusBadge.textContent = 'Active & Monitoring';
          toggleWatcherBtn.textContent = 'Stop Auto-Ingestion';
          toggleWatcherBtn.className = 'btn btn-sm btn-danger';
        } else {
          watcherStatusBadge.className = 'badge badge-warning';
          watcherStatusBadge.textContent = 'Inactive';
          toggleWatcherBtn.textContent = 'Start Auto-Ingestion';
          toggleWatcherBtn.className = 'btn btn-sm btn-primary';
        }
        watcherFolderText.textContent = activeEvent.watched_folder ? `📁 ${activeEvent.watched_folder}` : 'No watched folder configured';
        watcherStatsText.textContent = status.is_active
          ? `Processed: ${status.files_processed} files | Errors: ${status.errors} | Last scanned: ${status.last_scanned_at ? new Date(status.last_scanned_at).toLocaleTimeString() : 'scanning...'}`
          : '';
      }
    } catch {}
  }

  toggleWatcherBtn.addEventListener('click', async () => {
    if (!activeEvent.watched_folder) {
      alert('Please configure a watched folder in Settings first.');
      return;
    }
    const currentActive = watcherStatusBadge.textContent.includes('Active');
    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}/watcher-toggle?active=${!currentActive}`, {
        method: 'POST'
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Failed to toggle watcher');
      }
      activeEvent.watched_folder_active = !currentActive;
      updateWatcherUI();
    } catch (err) {
      alert(err.message);
    }
  });

  // --- Audit Logs View ---
  viewAuditLogsBtn.addEventListener('click', async () => {
    auditModal.classList.add('active');
    auditLogsContainer.innerHTML = 'Loading audit logs...';
    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}/audit-logs?limit=50`);
      if (!resp.ok) throw new Error('Failed to load logs');
      const logs = await resp.json();
      if (logs.length === 0) {
        auditLogsContainer.innerHTML = 'No ingestion logs recorded yet.';
        return;
      }
      auditLogsContainer.innerHTML = logs.map((l) => {
        const dt = new Date(l.created_at).toLocaleTimeString();
        const color = l.status === 'success' ? '#34d399' : l.status === 'duplicate' ? '#fbbf24' : '#f87171';
        return `<div><span style="color: #9ca3af;">[${dt}]</span> [${l.source}] <strong style="color: ${color};">[${l.status.toUpperCase()}]</strong> ${l.filename} - ${l.message || ''}</div>`;
      }).join('');
    } catch (err) {
      auditLogsContainer.innerHTML = `<span style="color: #ef4444;">Error: ${err.message}</span>`;
    }
  });
  closeAuditModalBtn.addEventListener('click', () => auditModal.classList.remove('active'));

  // --- Event Photos Grid & Deletion ---
  async function loadEventPhotos() {
    photosGrid.innerHTML = '<div style="color: var(--text-muted);">Loading photos...</div>';
    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}/photos?page=1&page_size=100`);
      if (!resp.ok) throw new Error('Failed to load event photos');
      const data = await resp.json();

      photoCountSpan.textContent = data.total;
      let totalFaces = 0;
      data.items.forEach((p) => { totalFaces += p.face_count || 0; });
      faceCountSpan.textContent = `${totalFaces} faces indexed`;

      if (data.items.length === 0) {
        photosGrid.innerHTML = `
          <div style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: var(--text-muted);">
            No photos in this event yet. Drag and drop photos above or start camera tethering.
          </div>
        `;
        return;
      }

      photosGrid.innerHTML = '';
      data.items.forEach((p) => {
        const item = document.createElement('div');
        item.className = 'photo-item';
        const thumbUrl = `/api/media/${p.id}/thumbnail?token=${encodeURIComponent(authToken)}`;

        item.innerHTML = `
          <img src="${thumbUrl}" alt="${p.filename}">
          <span class="photo-badge">👤 ${p.face_count}</span>
          <button class="btn btn-sm btn-danger" style="position: absolute; bottom: 6px; right: 6px; padding: 2px 6px; font-size: 0.7rem; border-radius: 4px;" title="Delete Photo">✕</button>
        `;

        const delBtn = item.querySelector('button');
        delBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (confirm(`Delete photo "${p.filename}" permanently? This purges all face embeddings and storage files.`)) {
            await deletePhoto(p.id);
          }
        });

        photosGrid.appendChild(item);
      });
    } catch (err) {
      photosGrid.innerHTML = `<div class="text-danger">${err.message}</div>`;
    }
  }

  async function deletePhoto(photoId) {
    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}/photos/${photoId}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error('Failed to delete photo');
      loadEventPhotos();
    } catch (err) {
      alert(err.message);
    }
  }

  // --- Bulk File Upload & Deduplication ---
  browseFilesBtn.addEventListener('click', () => bulkFileInput.click());
  bulkFileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      uploadFiles(Array.from(e.target.files));
      e.target.value = '';
    }
  });

  photoDropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    photoDropZone.classList.add('dragover');
  });
  photoDropZone.addEventListener('dragleave', () => photoDropZone.classList.remove('dragover'));
  photoDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    photoDropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      uploadFiles(Array.from(e.dataTransfer.files));
    }
  });

  async function uploadFiles(files) {
    uploadProgress.classList.remove('d-none');
    uploadProgress.textContent = `Ingesting ${files.length} photo(s)... Extracting EXIF and indexing faces...`;

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}/photos/upload`, {
        method: 'POST',
        body: formData
      });
      if (!resp.ok) throw new Error('Upload failed');
      const uploaded = await resp.json();
      uploadProgress.textContent = `Successfully processed ${uploaded.length} photo(s).`;
      setTimeout(() => uploadProgress.classList.add('d-none'), 3000);
      loadEventPhotos();
    } catch (err) {
      uploadProgress.textContent = `Upload error: ${err.message}`;
    }
  }

  // --- Event Creation & Editing ---
  newEventBtn.addEventListener('click', () => {
    activeEvent = null;
    eventModalTitle.textContent = 'Create New Event';
    eventForm.reset();
    eventDateInput.valueAsDate = new Date();
    eventModal.classList.add('active');
  });

  editSettingsBtn.addEventListener('click', () => {
    if (!activeEvent) return;
    eventModalTitle.textContent = 'Edit Event Settings';
    eventTitleInput.value = activeEvent.title;
    eventVenueInput.value = activeEvent.venue || '';
    if (activeEvent.event_date) {
      eventDateInput.value = activeEvent.event_date.split('T')[0];
    }
    eventPinInput.value = activeEvent.pin_code || '';
    strictSelfieModeInput.checked = Boolean(activeEvent.strict_selfie_mode);
    watchedFolderInput.value = activeEvent.watched_folder || '';
    eventModal.classList.add('active');
  });

  cancelEventModalBtn.addEventListener('click', () => eventModal.classList.remove('active'));

  eventForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      title: eventTitleInput.value.trim(),
      venue: eventVenueInput.value.trim() || null,
      event_date: eventDateInput.value ? new Date(eventDateInput.value).toISOString() : null,
      pin_code: eventPinInput.value.trim() || null,
      strict_selfie_mode: strictSelfieModeInput.checked,
      watched_folder: watchedFolderInput.value.trim() || null
    };

    try {
      if (activeEvent && activeEvent.id) {
        // Update existing event
        const resp = await apiFetch(`/api/events/${activeEvent.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error('Update failed');
        activeEvent = await resp.json();
      } else {
        // Create new event
        const resp = await apiFetch('/api/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error('Create failed');
      }
      eventModal.classList.remove('active');
      if (activeEvent && activeEvent.id) {
        openEventDetail(activeEvent);
      } else {
        loadEvents();
      }
    } catch (err) {
      alert(err.message);
    }
  });

  // --- Event Deletion with Full Cascade Purge ---
  deleteEventBtn.addEventListener('click', async () => {
    if (!activeEvent) return;
    const confirmed = confirm(
      `⚠️ FULL CASCADE PURGE:\nAre you sure you want to delete "${activeEvent.title}"?\n\n` +
      `This will permanently purge:\n` +
      `• All uploaded and tethered photos\n` +
      `• All AI biometric face embeddings\n` +
      `• All original, preview, and thumbnail files from disk\n\n` +
      `This action cannot be undone.`
    );
    if (!confirmed) return;

    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error('Delete failed');
      activeEvent = null;
      loadEvents();
    } catch (err) {
      alert(err.message);
    }
  });

  // --- Guest QR Code & Share Link ---
  let cachedNetInfo = null;

  async function getNetworkInfo() {
    if (!cachedNetInfo) {
      try {
        const resp = await apiFetch('/api/events/system/network-info');
        if (resp.ok) {
          cachedNetInfo = await resp.json();
        }
      } catch {}
    }
    return cachedNetInfo || { lan_url: window.location.origin, local_ip: '127.0.0.1' };
  }

  const qrNetworkSelect = document.getElementById('qrNetworkSelect');
  const customHostGroup = document.getElementById('customHostGroup');
  const customHostInput = document.getElementById('customHostInput');

  function getSelectedBaseUrl(netInfo) {
    const mode = qrNetworkSelect ? qrNetworkSelect.value : 'lan';
    if (mode === 'lan' && netInfo && netInfo.lan_url) {
      return netInfo.lan_url;
    } else if (mode === 'custom' && customHostInput && customHostInput.value.trim()) {
      return customHostInput.value.trim().replace(/\/+$/, '');
    }
    return window.location.origin;
  }

  async function updateQrView() {
    if (!activeEvent) return;
    const netInfo = await getNetworkInfo();
    const selectedBase = getSelectedBaseUrl(netInfo);
    const guestUrl = `${selectedBase}/guest?token=${activeEvent.guest_token}`;

    const pngUrl = `/api/events/${activeEvent.id}/qr.png?token=${encodeURIComponent(authToken)}&base_url=${encodeURIComponent(selectedBase)}&t=${Date.now()}`;
    const svgUrl = `/api/events/${activeEvent.id}/qr.svg?token=${encodeURIComponent(authToken)}&base_url=${encodeURIComponent(selectedBase)}&t=${Date.now()}`;

    qrImage.src = pngUrl;
    guestShareUrlInput.value = guestUrl;
    downloadQrPngBtn.href = pngUrl;
    downloadQrSvgBtn.href = svgUrl;
  }

  if (qrNetworkSelect) {
    qrNetworkSelect.addEventListener('change', () => {
      if (customHostGroup) {
        customHostGroup.classList.toggle('d-none', qrNetworkSelect.value !== 'custom');
      }
      updateQrView();
    });
  }

  if (customHostInput) {
    customHostInput.addEventListener('input', updateQrView);
  }

  showQrBtn.addEventListener('click', async () => {
    if (!activeEvent) return;
    const netInfo = await getNetworkInfo();
    if (qrNetworkSelect && netInfo && netInfo.lan_url) {
      const lanOption = qrNetworkSelect.querySelector('option[value="lan"]');
      if (lanOption) {
        lanOption.textContent = `📶 Venue Wi-Fi (${netInfo.local_ip || 'LAN IP'})`;
      }
    }
    await updateQrView();
    qrModal.classList.add('active');
  });

  closeQrModalBtn.addEventListener('click', () => qrModal.classList.remove('active'));

  copyShareUrlBtn.addEventListener('click', () => {
    guestShareUrlInput.select();
    navigator.clipboard.writeText(guestShareUrlInput.value).then(() => {
      copyShareUrlBtn.textContent = '✓ Copied!';
      setTimeout(() => copyShareUrlBtn.textContent = '📋 Copy Link', 2000);
    });
  });

  // Security Kill-Switch: Revoke & Regenerate Token
  revokeTokenBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to revoke the guest token? All previously printed or shared QR codes and links will become completely invalid immediately.')) {
      return;
    }
    try {
      const resp = await apiFetch(`/api/events/${activeEvent.id}/regenerate-token`, { method: 'POST' });
      if (!resp.ok) throw new Error('Token regeneration failed');
      activeEvent = await resp.json();
      await updateQrView();
      alert('Guest token revoked and regenerated successfully. New link is active.');
    } catch (err) {
      alert(err.message);
    }
  });

  // Initialize Session
  checkSession();
})();
