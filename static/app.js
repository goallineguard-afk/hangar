const dock = document.getElementById('dock');
const fileInput = document.getElementById('fileInput');
const manifestBody = document.getElementById('manifestBody');
const emptyState = document.getElementById('emptyState');
const statsEl = document.getElementById('stats');
const searchEl = document.getElementById('search');
const folderFilterEl = document.getElementById('folderFilter');
const progressWrap = document.getElementById('dockProgress');
const progressBar = document.getElementById('dockProgressBar');
const progressLabel = document.getElementById('dockProgressLabel');
const toast = document.getElementById('toast');

let lastUploadedId = null;

function humanSize(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

function humanDate(iso) {
  const d = new Date(iso + 'Z');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
         d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function showToast(msg, isError) {
  toast.textContent = msg;
  toast.hidden = false;
  toast.className = 'toast' + (isError ? ' error' : '');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { toast.hidden = true; }, 3200);
}

async function loadFiles() {
  const params = new URLSearchParams();
  if (searchEl.value.trim()) params.set('q', searchEl.value.trim());
  else if (folderFilterEl.value) params.set('folder', folderFilterEl.value);

  const res = await fetch('/api/files?' + params.toString());
  const data = await res.json();

  statsEl.textContent = `${data.count} item${data.count === 1 ? '' : 's'} logged · ${humanSize(data.total_size)} stored`;

  // keep folder dropdown in sync without wiping the current selection
  const current = folderFilterEl.value;
  folderFilterEl.innerHTML = '<option value="">All folders</option>' +
    data.folders.map(f => `<option value="${f}">${f}</option>`).join('');
  folderFilterEl.value = current;

  manifestBody.innerHTML = '';
  emptyState.hidden = data.files.length > 0;

  for (const file of data.files) {
    manifestBody.appendChild(renderRow(file));
  }
}

function renderRow(file) {
  const row = document.createElement('div');
  row.className = 'manifest-row';
  if (file.id === lastUploadedId) {
    row.classList.add('new');
    lastUploadedId = null;
  }
  row.innerHTML = `
    <span class="col-id">${file.id}</span>
    <span class="col-name">${escapeHtml(file.name)}</span>
    <span class="col-tag">${file.category}</span>
    <span class="col-size">${humanSize(file.size)}</span>
    <span class="col-date">${humanDate(file.uploaded_at)}</span>
    <span class="col-actions">
      <button data-action="download">Get</button>
      <button data-action="share">Share</button>
      <button data-action="rename">Rename</button>
      <button data-action="delete" class="danger">Delete</button>
    </span>
  `;

  row.querySelector('[data-action="download"]').onclick = () => {
    window.location.href = `/api/download/${file.id}`;
  };
  row.querySelector('[data-action="share"]').onclick = async () => {
    const link = `${window.location.origin}/share/${file.share_token}`;
    try {
      await navigator.clipboard.writeText(link);
      showToast('Share link copied to clipboard.');
    } catch {
      showToast(link);
    }
  };
  row.querySelector('[data-action="rename"]').onclick = async () => {
    const name = prompt('Rename file', file.name);
    if (!name || name === file.name) return;
    const res = await fetch(`/api/files/${file.id}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (res.ok) { loadFiles(); } else { showToast('Rename failed.', true); }
  };
  row.querySelector('[data-action="delete"]').onclick = async () => {
    if (!confirm(`Remove "${file.name}" from Hangar?`)) return;
    const res = await fetch(`/api/files/${file.id}`, { method: 'DELETE' });
    if (res.ok) { loadFiles(); showToast('Removed.'); } else { showToast('Delete failed.', true); }
  };

  return row;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function uploadFiles(fileList) {
  for (const file of fileList) {
    await uploadOne(file);
  }
  loadFiles();
}

function uploadOne(file) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('file', file);
    form.append('folder', folderFilterEl.value || '/');

    progressWrap.hidden = false;
    progressLabel.textContent = `Sending ${file.name}…`;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = pct + '%';
        progressLabel.textContent = `Sending ${file.name}… ${pct}%`;
      }
    };
    xhr.onload = () => {
      progressWrap.hidden = true;
      progressBar.style.width = '0%';
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status === 200 && data.ok) {
          lastUploadedId = data.id;
          showToast(`${file.name} logged.`);
        } else {
          showToast(data.error || 'Upload failed.', true);
        }
      } catch {
        showToast('Upload failed.', true);
      }
      resolve();
    };
    xhr.onerror = () => {
      progressWrap.hidden = true;
      showToast('Upload failed — check your connection.', true);
      resolve();
    };
    xhr.open('POST', '/api/upload');
    xhr.send(form);
  });
}

dock.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) uploadFiles(fileInput.files);
  fileInput.value = '';
});
['dragenter', 'dragover'].forEach(evt =>
  dock.addEventListener(evt, (e) => { e.preventDefault(); dock.classList.add('dragover'); })
);
['dragleave', 'drop'].forEach(evt =>
  dock.addEventListener(evt, (e) => { e.preventDefault(); dock.classList.remove('dragover'); })
);
dock.addEventListener('drop', (e) => {
  if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
});

let searchDebounce;
searchEl.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(loadFiles, 250);
});
folderFilterEl.addEventListener('change', loadFiles);

loadFiles();
