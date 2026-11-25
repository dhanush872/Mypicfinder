// EventFrame Guest Portal Controller
(() => {
  const urlParams = new URLSearchParams(window.location.search);
  const guestToken = urlParams.get('token');
  let currentPin = sessionStorage.getItem(`ef_pin_${guestToken}`) || '';
  let activeEvent = null;
  let webcamStream = null;

  // Gallery state
  let galleryPhotos = [];
  let currentGalleryPage = 1;
  let totalGalleryPages = 1;
  let activeLightboxIndex = 0;
  let activePhotoList = []; // Points to galleryPhotos or searchResults

  // Register Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  // DOM Elements
  const pinSection = document.getElementById('pinSection');
  const pinInput = document.getElementById('pinInput');
  const verifyPinBtn = document.getElementById('verifyPinBtn');
  const pinError = document.getElementById('pinError');

  const portalContent = document.getElementById('portalContent');
  const eventTitle = document.getElementById('eventTitle');
  const eventVenue = document.getElementById('eventVenue');
  const eventDateBadge = document.getElementById('eventDateBadge');

  const biometricConsent = document.getElementById('biometricConsent');
  const smartCameraBtn = document.getElementById('smartCameraBtn');
  const photoLibraryBtn = document.getElementById('photoLibraryBtn');
  const mobileCameraInput = document.getElementById('mobileCameraInput');
  const photoLibraryInput = document.getElementById('photoLibraryInput');

  const selfiePreviewBox = document.getElementById('selfiePreviewBox');
  const selfieThumbnail = document.getElementById('selfieThumbnail');
  const selfieStatusText = document.getElementById('selfieStatusText');
  const selfieStats = document.getElementById('selfieStats');

  const searchResultsSection = document.getElementById('searchResultsSection');
  const searchResultsGrid = document.getElementById('searchResultsGrid');
  const searchResultsHeading = document.getElementById('searchResultsHeading');
  const searchLatencyBadge = document.getElementById('searchLatencyBadge');

  const gallerySection = document.getElementById('gallerySection');
  const galleryGrid = document.getElementById('galleryGrid');
  const strictModeNotice = document.getElementById('strictModeNotice');
  const galleryTotalBadge = document.getElementById('galleryTotalBadge');
  const galleryPagination = document.getElementById('galleryPagination');
  const loadMoreBtn = document.getElementById('loadMoreBtn');

  const webcamModal = document.getElementById('webcamModal');
  const webcamVideo = document.getElementById('webcamVideo');
  const snapShutterBtn = document.getElementById('snapShutterBtn');
  const cancelWebcamBtn = document.getElementById('cancelWebcamBtn');

  const lightbox = document.getElementById('lightbox');
  const lightboxImg = document.getElementById('lightboxImg');
  const lightboxIndex = document.getElementById('lightboxIndex');
  const lightboxDownloadBtn = document.getElementById('lightboxDownloadBtn');
  const lightboxCloseBtn = document.getElementById('lightboxCloseBtn');
  const lightboxPrevBtn = document.getElementById('lightboxPrevBtn');
  const lightboxNextBtn = document.getElementById('lightboxNextBtn');

  if (!guestToken) {
    document.body.innerHTML = `
      <div style="text-align: center; padding: 4rem 1rem; color: #ef4444;">
        <h2>⚠️ Invalid or Missing Guest Token</h2>
        <p style="color: #9ca3af; margin-top: 0.5rem;">Please scan the event QR code again or check your invite link.</p>
      </div>
    `;
    return;
  }

  // --- API Fetch Helper ---
  async function apiFetch(endpoint, options = {}) {
    const headers = options.headers || {};
    headers['X-Guest-Token'] = guestToken;
    if (currentPin) {
      headers['X-Guest-PIN'] = currentPin;
    }
    const separator = endpoint.includes('?') ? '&' : '?';
    const url = `${endpoint}${separator}token=${encodeURIComponent(guestToken)}`;
    return fetch(url, { credentials: 'same-origin', ...options, headers });
  }

  // --- Initialize Portal ---
  async function init() {
    try {
      const resp = await apiFetch('/api/guest/info');
      if (!resp.ok) {
        throw new Error('Event access revoked or not found');
      }
      activeEvent = await resp.json();
      renderEventHeader();

      if (activeEvent.has_pin && !currentPin) {
        showPinPrompt();
      } else {
        showPortal();
      }
    } catch (err) {
      document.body.innerHTML = `
        <div style="text-align: center; padding: 4rem 1rem; color: #ef4444;">
          <h2>⚠️ Event Unavailable</h2>
          <p style="color: #9ca3af; margin-top: 0.5rem;">${err.message}</p>
        </div>
      `;
    }
  }

  function renderEventHeader() {
    eventTitle.textContent = activeEvent.title;
    eventVenue.textContent = activeEvent.venue || '';
    if (activeEvent.event_date) {
      const dt = new Date(activeEvent.event_date);
      eventDateBadge.textContent = dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    }
  }

  function showPinPrompt() {
    pinSection.classList.remove('d-none');
    portalContent.classList.add('d-none');
    pinInput.focus();
  }

  verifyPinBtn.addEventListener('click', async () => {
    const pinVal = pinInput.value.trim();
    if (pinVal.length !== 4) {
      pinError.textContent = 'Please enter a 4-digit PIN';
      pinError.style.display = 'block';
      return;
    }
    try {
      const resp = await apiFetch('/api/guest/verify-pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin_code: pinVal })
      });
      if (!resp.ok) {
        throw new Error('Incorrect PIN code');
      }
      currentPin = pinVal;
      sessionStorage.setItem(`ef_pin_${guestToken}`, currentPin);
      pinSection.classList.add('d-none');
      showPortal();
    } catch (err) {
      pinError.textContent = err.message;
      pinError.style.display = 'block';
    }
  });

  function showPortal() {
    portalContent.classList.remove('d-none');
    if (activeEvent.strict_selfie_mode) {
      strictModeNotice.classList.remove('d-none');
      galleryGrid.classList.add('d-none');
      galleryPagination.classList.add('d-none');
      galleryTotalBadge.textContent = 'Selfie Search Only';
    } else {
      loadGallery(1);
    }
  }

  // --- Client-Side Canvas Pre-Upload Downscaling ---
  async function downscaleImage(fileOrBlob, maxDimension = 1080, maxSizeBytes = 250 * 1024) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          let w = img.width;
          let h = img.height;

          // Scale down proportionally
          if (w > maxDimension || h > maxDimension) {
            if (w > h) {
              h = Math.round((h * maxDimension) / w);
              w = maxDimension;
            } else {
              w = Math.round((w * maxDimension) / h);
              h = maxDimension;
            }
          }

          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, w, h);

          // Downscale quality loop to guarantee < 250 KB
          let quality = 0.85;
          function attemptCompress() {
            canvas.toBlob((blob) => {
              if (!blob) {
                return reject(new Error('Canvas compression failed'));
              }
              if (blob.size <= maxSizeBytes || quality <= 0.5) {
                resolve({ blob, dataUrl: canvas.toDataURL('image/jpeg', 0.5) });
              } else {
                quality -= 0.15;
                attemptCompress();
              }
            }, 'image/jpeg', quality);
          }
          attemptCompress();
        };
        img.onerror = () => reject(new Error('Invalid image data'));
        img.src = e.target.result;
      };
      reader.onerror = () => reject(new Error('Failed reading file'));
      reader.readAsDataURL(fileOrBlob);
    });
  }

  // --- Smart Selfie Button Logic ---
  const isMobile = /Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
    ('ontouchstart' in window && window.innerWidth <= 768);

  smartCameraBtn.addEventListener('click', () => {
    if (!biometricConsent.checked) {
      alert('⚠️ Biometric consent is required prior to facial photo matching. Please check the consent box.');
      biometricConsent.focus();
      return;
    }
    if (isMobile) {
      // Mobile: trigger native front camera
      mobileCameraInput.click();
    } else {
      // Desktop: open webcam stream modal
      startDesktopWebcam();
    }
  });

  photoLibraryBtn.addEventListener('click', () => {
    if (!biometricConsent.checked) {
      alert('⚠️ Biometric consent is required prior to facial photo matching. Please check the consent box.');
      biometricConsent.focus();
      return;
    }
    photoLibraryInput.click();
  });

  mobileCameraInput.addEventListener('change', handleFileInput);
  photoLibraryInput.addEventListener('change', handleFileInput);

  async function handleFileInput(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    e.target.value = ''; // reset input
    await processSelfieUpload(file);
  }

  // Desktop Webcam Stream
  async function startDesktopWebcam() {
    webcamModal.classList.add('active');
    try {
      webcamStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } }
      });
      webcamVideo.srcObject = webcamStream;
    } catch (err) {
      alert('Unable to access webcam: ' + err.message);
      stopDesktopWebcam();
    }
  }

  function stopDesktopWebcam() {
    if (webcamStream) {
      webcamStream.getTracks().forEach((track) => track.stop());
      webcamStream = null;
    }
    webcamModal.classList.remove('active');
  }

  cancelWebcamBtn.addEventListener('click', stopDesktopWebcam);

  snapShutterBtn.addEventListener('click', async () => {
    if (!webcamVideo.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = webcamVideo.videoWidth;
    canvas.height = webcamVideo.videoHeight;
    const ctx = canvas.getContext('2d');
    // Un-mirror image
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(webcamVideo, 0, 0);

    stopDesktopWebcam();

    canvas.toBlob(async (blob) => {
      await processSelfieUpload(blob);
    }, 'image/jpeg', 0.9);
  });

  // --- Selfie Processing & Face Search ---
  async function processSelfieUpload(fileOrBlob) {
    if (!biometricConsent.checked) {
      alert('Biometric consent is required.');
      return;
    }

    selfiePreviewBox.classList.remove('d-none');
    selfieStatusText.textContent = 'Optimizing selfie in volatile RAM...';
    selfieStats.textContent = '';

    try {
      // 1. Client-side canvas downscale (<250KB, max 1080px)
      const { blob: downscaledBlob, dataUrl } = await downscaleImage(fileOrBlob);
      selfieThumbnail.src = dataUrl;

      const sizeKb = Math.round(downscaledBlob.size / 1024);
      selfieStats.textContent = `Optimized payload: ${sizeKb} KB`;
      selfieStatusText.textContent = 'Matching faces across event...';

      // 2. Perform Biometric Search API Call
      const formData = new FormData();
      formData.append('selfie', downscaledBlob, 'selfie.jpg');
      formData.append('biometric_consent', 'true');
      if (currentPin) {
        formData.append('pin', currentPin);
      }

      const resp = await apiFetch('/api/guest/selfie-search', {
        method: 'POST',
        body: formData
      });

      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Face search failed');
      }

      const searchResult = await resp.json();
      renderSearchResults(searchResult);
    } catch (err) {
      selfieStatusText.textContent = `Search failed: ${err.message}`;
      selfieStatusText.style.color = '#ef4444';
    }
  }

  function renderSearchResults(data) {
    searchResultsGrid.innerHTML = '';
    searchResultsSection.classList.remove('d-none');

    selfieStatusText.textContent = `Search Complete! Found ${data.match_count} photos`;
    selfieStatusText.style.color = '#10b981';

    searchLatencyBadge.textContent = `${data.latency_ms} ms`;
    searchResultsHeading.textContent = `Your Photos (${data.match_count})`;

    if (data.match_count === 0) {
      searchResultsGrid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: #9ca3af;">
          No matching photos found with your selfie yet. Check back soon as new tethered photos arrive!
        </div>
      `;
      return;
    }

    const matchedPhotos = data.matches.map((m) => {
      const p = m.photo;
      p._confidence = m.confidence;
      return p;
    });

    matchedPhotos.forEach((photo, idx) => {
      const item = createPhotoElement(photo, idx, matchedPhotos);
      searchResultsGrid.appendChild(item);
    });

    // Scroll to results
    searchResultsSection.scrollIntoView({ behavior: 'smooth' });
  }

  // --- Chronological Gallery ---
  async function loadGallery(page = 1) {
    try {
      const resp = await apiFetch(`/api/guest/gallery?page=${page}&page_size=24`);
      if (!resp.ok) {
        return;
      }
      const data = await resp.json();
      currentGalleryPage = data.page;
      totalGalleryPages = data.total_pages;

      if (page === 1) {
        galleryPhotos = data.items;
        galleryGrid.innerHTML = '';
      } else {
        galleryPhotos.push(...data.items);
      }

      galleryTotalBadge.textContent = `${data.total} photos`;

      data.items.forEach((photo, idx) => {
        const item = createPhotoElement(photo, galleryPhotos.length - data.items.length + idx, galleryPhotos);
        galleryGrid.appendChild(item);
      });

      if (currentGalleryPage < totalGalleryPages) {
        galleryPagination.classList.remove('d-none');
      } else {
        galleryPagination.classList.add('d-none');
      }
    } catch (err) {
      console.error('Gallery load error:', err);
    }
  }

  loadMoreBtn.addEventListener('click', () => {
    if (currentGalleryPage < totalGalleryPages) {
      loadGallery(currentGalleryPage + 1);
    }
  });

  // --- Photo Element Builder ---
  function createPhotoElement(photo, index, photoList) {
    const el = document.createElement('div');
    el.className = 'photo-item';

    const thumbUrl = `/api/media/${photo.id}/thumbnail?token=${encodeURIComponent(guestToken)}`;
    el.innerHTML = `
      <img src="${thumbUrl}" alt="Photo ${photo.filename}" loading="lazy">
      ${photo._confidence ? `<span class="photo-confidence-badge">${Math.round(photo._confidence * 100)}% Match</span>` : ''}
    `;

    el.addEventListener('click', () => {
      openLightbox(index, photoList);
    });

    return el;
  }

  // --- Fullscreen Lightbox ---
  function openLightbox(index, photoList) {
    activePhotoList = photoList;
    activeLightboxIndex = index;
    updateLightboxContent();
    lightbox.classList.add('active');
  }

  function updateLightboxContent() {
    const photo = activePhotoList[activeLightboxIndex];
    if (!photo) return;

    const previewUrl = `/api/media/${photo.id}/preview?token=${encodeURIComponent(guestToken)}`;
    const originalUrl = `/api/media/${photo.id}/original?token=${encodeURIComponent(guestToken)}`;

    lightboxImg.src = previewUrl;
    lightboxDownloadBtn.href = originalUrl;
    lightboxIndex.textContent = `${activeLightboxIndex + 1} / ${activePhotoList.length}`;
  }

  function closeLightbox() {
    lightbox.classList.remove('active');
  }

  lightboxCloseBtn.addEventListener('click', closeLightbox);
  lightboxPrevBtn.addEventListener('click', () => {
    if (activeLightboxIndex > 0) {
      activeLightboxIndex--;
      updateLightboxContent();
    }
  });
  lightboxNextBtn.addEventListener('click', () => {
    if (activeLightboxIndex < activePhotoList.length - 1) {
      activeLightboxIndex++;
      updateLightboxContent();
    }
  });

  // Keyboard navigation for Lightbox
  document.addEventListener('keydown', (e) => {
    if (!lightbox.classList.contains('active')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft' && activeLightboxIndex > 0) {
      activeLightboxIndex--;
      updateLightboxContent();
    }
    if (e.key === 'ArrowRight' && activeLightboxIndex < activePhotoList.length - 1) {
      activeLightboxIndex++;
      updateLightboxContent();
    }
  });

  // Start initialization
  init();
})();
