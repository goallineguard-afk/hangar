const shelfList = document.getElementById('shelfList');
const catalog = document.getElementById('catalog');
const libEmpty = document.getElementById('libEmpty');
const librarySearch = document.getElementById('librarySearch');
const allCount = document.getElementById('allCount');

let currentShelf = '';
let allShelves = [];

function humanSize(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function loadLibrary() {
  const params = new URLSearchParams();
  if (librarySearch.value.trim()) params.set('q', librarySearch.value.trim());
  else if (currentShelf) params.set('folder', currentShelf);

  const res = await fetch('/api/library/files?' + params.toString());
  const data = await res.json();

  if (!librarySearch.value.trim()) {
    renderShelves(data.shelves);
  }

  catalog.innerHTML = '';
  libEmpty.hidden = data.files.length > 0;

  for (const file of data.files) {
    catalog.appendChild(renderCard(file));
  }
}

function renderShelves(shelves) {
  allShelves = shelves;
  const total = shelves.reduce((sum, s) => sum + s.count, 0);
  allCount.textContent = total;

  const items = shelves.map(s => `
    <li class="shelf-item ${s.name === currentShelf ? 'active' : ''}" data-shelf="${escapeHtml(s.name)}">
      ${escapeHtml(s.name === '/' ? 'Unsorted' : s.name)}
      <span class="shelf-count mono">${s.count}</span>
    </li>
  `).join('');

  shelfList.innerHTML = `
    <li class="shelf-item ${currentShelf === '' ? 'active' : ''}" data-shelf="">
      All items <span class="shelf-count mono" id="allCount">${total}</span>
    </li>
    ${items}
  `;

  shelfList.querySelectorAll('.shelf-item').forEach(el => {
    el.addEventListener('click', () => {
      currentShelf = el.dataset.shelf;
      librarySearch.value = '';
      loadLibrary();
    });
  });
}

function renderCard(file) {
  const card = document.createElement('div');
  card.className = 'catalog-card';
  card.innerHTML = `
    <div class="catalog-tag mono">${file.category}</div>
    <div class="catalog-name">${escapeHtml(file.name)}</div>
    <div class="catalog-meta mono">${file.folder === '/' ? 'Unsorted' : escapeHtml(file.folder)} &middot; ${humanSize(file.size)}</div>
    <a class="catalog-download" href="/library/download/${file.id}">Download</a>
  `;
  return card;
}

let searchDebounce;
librarySearch.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(loadLibrary, 250);
});

loadLibrary();
