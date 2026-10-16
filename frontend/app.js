/**
 * DALAL STREET PULSE - CLIENT APPLICATION JAVASCRIPT
 * Real-time automated Indian Financial News Engine
 */

(function () {
  'use strict';

  // Application State
  const state = {
    articles: [],
    allLoadedArticles: [],
    stats: null,
    currentType: 'important', // DEFAULT: Important News
    currentSource: 'All',
    currentSentiment: 'All',
    searchQuery: '',
    isLoading: false,
    lastFetchedAt: null,
    autoRefreshIntervalSec: 60, // 1 minute auto-sync
    secondsRemaining: 60,
    timerId: null,
    searchDebounceTimer: null,
    theme: 'dark',
    bookmarks: JSON.parse(localStorage.getItem('dalal_bookmarks') || '[]'),
    keyEvents: [],
    economicEvents: [],
    holidayEvents: [],
    currentCalendarSubtab: 'economic',
    calendarCountry: 'All',
    calendarImpact: 'All',
    calendarSearch: '',
    speechPlayingId: null,
    speechUtterance: null,
    activeModalArticle: null,
    connectionFailureCount: 0
  };

  // DOM Element References
  const dom = {
    newsGrid: document.getElementById('newsGrid'),
    skeletonGrid: document.getElementById('skeletonGrid'),
    emptyState: document.getElementById('emptyState'),
    eventsWrapper: document.getElementById('eventsWrapper'),
    feedWrapper: document.getElementById('feedWrapper'),
    filterActionsBar: document.getElementById('filterActionsBar'),
    calendarControlsBar: document.getElementById('calendarControlsBar'),
    paneEconomic: document.getElementById('paneEconomic'),
    paneHolidays: document.getElementById('paneHolidays'),
    panePolicy: document.getElementById('panePolicy'),
    economicCalendarTbody: document.getElementById('economicCalendarTbody'),
    holidaysCalendarTbody: document.getElementById('holidaysCalendarTbody'),
    eventsGrid: document.getElementById('eventsGrid'),
    calendarSubtabs: document.querySelectorAll('.calendar-subtab'),
    calendarCountryFilter: document.getElementById('calendarCountryFilter'),
    calendarImpactFilter: document.getElementById('calendarImpactFilter'),
    calendarSearchInput: document.getElementById('calendarSearchInput'),
    countEconomicCal: document.getElementById('countEconomicCal'),
    countHolidaysCal: document.getElementById('countHolidaysCal'),
    countPolicyCal: document.getElementById('countPolicyCal'),
    lastUpdatedTime: document.getElementById('lastUpdatedTime'),
    refreshBtn: document.getElementById('refreshBtn'),
    autoRefreshCountdown: document.getElementById('autoRefreshCountdown'),
    marketStatusPill: document.getElementById('marketStatusPill'),
    marketStatusDot: document.getElementById('marketStatusDot'),
    marketStatusText: document.getElementById('marketStatusText'),
    statTotalArticles: document.getElementById('statTotalArticles'),
    statBullishCount: document.getElementById('statBullishCount'),
    statBearishCount: document.getElementById('statBearishCount'),
    sourceTabs: document.querySelectorAll('.source-tab'),
    sentimentPills: document.querySelectorAll('.sentiment-pill'),
    searchInput: document.getElementById('searchInput'),
    clearSearchBtn: document.getElementById('clearSearchBtn'),
    activeQueryBar: document.getElementById('activeQueryBar'),
    activeQueryText: document.getElementById('activeQueryText'),
    resetFiltersBtn: document.getElementById('resetFiltersBtn'),
    emptyResetBtn: document.getElementById('emptyResetBtn'),
    badgeImportant: document.getElementById('badgeImportant'),
    badgeAll: document.getElementById('badgeAll'),
    badgeFilings: document.getElementById('badgeFilings'),
    badgeIndian: document.getElementById('badgeIndian'),
    badgeInternational: document.getElementById('badgeInternational'),
    badgeTrump: document.getElementById('badgeTrump'),
    badgeEvents: document.getElementById('badgeEvents'),
    badgeBookmarks: document.getElementById('badgeBookmarks'),
    sourceTabGroups: document.querySelectorAll('.source-tab-group'),
    dropdownTriggers: document.querySelectorAll('.tab-dropdown-trigger'),
    dropdownItems: document.querySelectorAll('.dropdown-item'),
    dropdownBackdrop: document.getElementById('dropdownBackdrop'),
    marketTickerTrack: document.getElementById('marketTickerTrack'),
    toastContainer: document.getElementById('toastContainer'),
    backToTopBtn: document.getElementById('backToTopBtn'),
    connectionBanner: document.getElementById('connectionBanner'),
    bannerRetryBtn: document.getElementById('bannerRetryBtn'),
    themeToggleBtn: document.getElementById('themeToggleBtn'),
    themeIconDark: document.querySelector('.theme-icon-dark'),
    themeIconLight: document.querySelector('.theme-icon-light'),
    liveClockText: document.getElementById('liveClockText'),
    tldrModalOverlay: document.getElementById('tldrModalOverlay'),
    tldrModalCloseBtn: document.getElementById('tldrModalCloseBtn'),
    tldrModalTitle: document.getElementById('tldrModalTitle'),
    tldrBulletsList: document.getElementById('tldrBulletsList'),
    tldrListenBtn: document.getElementById('tldrListenBtn'),
    tldrListenText: document.getElementById('tldrListenText'),
    tldrReadFullBtn: document.getElementById('tldrReadFullBtn'),
    shareModalOverlay: document.getElementById('shareModalOverlay'),
    shareModalCloseBtn: document.getElementById('shareModalCloseBtn'),
    sharePreviewText: document.getElementById('sharePreviewText'),
    shareWhatsAppBtn: document.getElementById('shareWhatsAppBtn'),
    shareTelegramBtn: document.getElementById('shareTelegramBtn'),
    shareCopyLinkBtn: document.getElementById('shareCopyLinkBtn'),
    shareCopyLabel: document.getElementById('shareCopyLabel'),
    pushToggleBtn: document.getElementById('pushToggleBtn'),
    pushIcon: document.getElementById('pushIcon'),
    pushLabel: document.getElementById('pushLabel'),
    installPwaBtn: document.getElementById('installPwaBtn'),
    installModalOverlay: document.getElementById('installModalOverlay'),
    installModalCloseBtn: document.getElementById('installModalCloseBtn'),
    installModalDismissBtn: document.getElementById('installModalDismissBtn'),
    iosInstallGuide: document.getElementById('iosInstallGuide'),
    generalInstallGuide: document.getElementById('generalInstallGuide')
  };

  // ---------------------------------------------------------------------------
  // Time & Market Utilities (Indian Standard Time: UTC+5:30)
  // ---------------------------------------------------------------------------

  function getISTDate() {
    const now = new Date();
    // Offset in milliseconds for IST (UTC+5:30)
    const istOffsetMs = 5.5 * 60 * 60 * 1000;
    const utcTimeMs = now.getTime() + (now.getTimezoneOffset() * 60 * 1000);
    return new Date(utcTimeMs + istOffsetMs);
  }

  function updateLiveClock() {
    if (!dom.liveClockText) return;
    const ist = getISTDate();
    const hours = ist.getHours();
    const minutes = ist.getMinutes();
    const seconds = ist.getSeconds();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    const str = `${String(displayHours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')} ${ampm}`;
    dom.liveClockText.textContent = str;
  }

  function updateMarketStatus() {
    const ist = getISTDate();
    const day = ist.getDay(); // 0 = Sun, 6 = Sat
    const hours = ist.getHours();
    const minutes = ist.getMinutes();
    const totalMinutes = hours * 60 + minutes;

    const isWeekday = day >= 1 && day <= 5;
    const preOpenStart = 9 * 60; // 09:00 AM
    const marketOpen = 9 * 60 + 15; // 09:15 AM
    const marketClose = 15 * 60 + 30; // 03:30 PM

    if (!dom.marketStatusPill) return;

    dom.marketStatusPill.className = 'market-status-pill';

    if (!isWeekday) {
      dom.marketStatusPill.classList.add('closed');
      dom.marketStatusText.textContent = 'NSE/BSE CLOSED (WEEKEND)';
    } else if (totalMinutes >= preOpenStart && totalMinutes < marketOpen) {
      dom.marketStatusPill.classList.add('preopen');
      dom.marketStatusText.textContent = 'NSE/BSE PRE-OPEN (IST)';
    } else if (totalMinutes >= marketOpen && totalMinutes < marketClose) {
      dom.marketStatusPill.classList.add('open');
      dom.marketStatusText.textContent = 'NSE/BSE LIVE TRADING';
    } else {
      dom.marketStatusPill.classList.add('closed');
      dom.marketStatusText.textContent = 'NSE/BSE CLOSED (IST)';
    }
  }

  function formatRelativeTime(dateInput) {
    if (!dateInput) return 'Recently';
    const date = new Date(dateInput);
    if (isNaN(date.getTime())) return 'Recently';

    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 45) return 'Just now';
    if (diffSec < 90) return '1m ago';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 7200) return '1h ago';
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 172800) return 'Yesterday';
    return `${Math.floor(diffSec / 86400)}d ago`;
  }

  function formatTimeOnly(date) {
    if (!date) return '';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  // ---------------------------------------------------------------------------
  // Toast Notifications
  // ---------------------------------------------------------------------------
  function showToast(message, icon = 'ℹ️') {
    if (!dom.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }

  // ---------------------------------------------------------------------------
  // Market Indices Ribbon Poller & Instant Fallbacks
  // ---------------------------------------------------------------------------
  const DEFAULT_FALLBACK_INDICES = [
    { name: 'NIFTY 50', symbol: '^NSEI', category: 'INDIA', price: 24055.80, change: -119.90, change_percent: -0.50, currency: '₹' },
    { name: 'SENSEX', symbol: '^BSESN', category: 'INDIA', price: 76944.28, change: -320.22, change_percent: -0.41, currency: '₹' },
    { name: 'BANK NIFTY', symbol: '^NSEBANK', category: 'INDIA', price: 57409.60, change: -86.70, change_percent: -0.15, currency: '₹' },
    { name: 'NASDAQ', symbol: '^IXIC', category: 'GLOBAL', price: 26370.89, change: -31.53, change_percent: -0.12, currency: '$' },
    { name: 'S&P 500', symbol: '^GSPC', category: 'GLOBAL', price: 7686.14, change: -25.62, change_percent: -0.33, currency: '$' },
    { name: 'DOW JONES', symbol: '^DJI', category: 'GLOBAL', price: 53185.90, change: -374.10, change_percent: -0.70, currency: '$' },
    { name: 'BRENT CRUDE', symbol: 'BZ=F', category: 'COMMODITY', price: 92.10, change: 1.61, change_percent: 1.78, currency: '$' },
    { name: 'GOLD', symbol: 'GC=F', category: 'COMMODITY', price: 4425.30, change: -56.20, change_percent: -1.25, currency: '$' },
    { name: 'USD/INR', symbol: 'INR=X', category: 'FOREX', price: 94.94, change: -0.21, change_percent: -0.22, currency: '₹' }
  ];

  async function fetchMarketIndices() {
    if (!dom.marketTickerTrack) return;
    if (!dom.marketTickerTrack.querySelector('.ticker-name') || dom.marketTickerTrack.textContent.includes('SYNCING')) {
      renderMarketIndices(DEFAULT_FALLBACK_INDICES);
    }
    try {
      const apiBase = getApiBaseUrl();
      const res = await fetch(`${apiBase}/api/market-indices`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.indices && data.indices.length > 0) {
        renderMarketIndices(data.indices);
      }
    } catch (e) {
      console.warn('Market indices fetch error:', e);
    }
  }

  const INDEX_SEARCH_MAP = {
    'NIFTY 50': 'Nifty',
    'SENSEX': 'Sensex',
    'BANK NIFTY': 'Bank',
    'NASDAQ': 'Nasdaq',
    'S&P 500': 'S&P',
    'DOW JONES': 'Dow',
    'BRENT CRUDE': 'Crude',
    'GOLD': 'Gold',
    'USD/INR': 'Rupee'
  };

  function renderMarketIndices(indices) {
    if (!dom.marketTickerTrack) return;

    const renderItems = (list) => list.map(item => {
      const isGain = item.change >= 0;
      const changeClass = isGain ? 'gain' : 'loss';
      const changeSign = isGain ? '+' : '';
      const priceStr = item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const cleanKeyword = INDEX_SEARCH_MAP[item.name] || item.name;

      return `
        <div class="ticker-item" data-search="${escapeHtml(cleanKeyword)}" title="Click to filter stories for ${escapeHtml(item.name)}">
          <span class="ticker-name">${escapeHtml(item.name)}</span>
          <span class="ticker-price">${escapeHtml(item.currency)}${priceStr}</span>
          <span class="ticker-change ${changeClass}">${changeSign}${item.change_percent.toFixed(2)}%</span>
        </div>
      `;
    }).join('');

    const rawHtml = renderItems(indices);
    dom.marketTickerTrack.innerHTML = rawHtml + rawHtml;

    dom.marketTickerTrack.querySelectorAll('.ticker-item').forEach(el => {
      el.addEventListener('click', () => {
        const query = el.getAttribute('data-search') || '';
        dom.searchInput.value = query;
        state.searchQuery = query;
        dom.clearSearchBtn.classList.remove('hidden');
        fetchNews(true);
        window.scrollTo({ top: 180, behavior: 'smooth' });
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Complete Economic Calendar & Market Holidays Suite
  // ---------------------------------------------------------------------------
  async function fetchEconomicCalendar() {
    try {
      const apiBase = getApiBaseUrl();
      const res = await fetch(`${apiBase}/api/calendar/economic`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.events) {
        state.economicEvents = data.events;
        if (dom.countEconomicCal) dom.countEconomicCal.textContent = data.events.length;
        if (dom.badgeEvents) dom.badgeEvents.textContent = data.events.length;
        renderEconomicCalendar();
      }
    } catch (e) {
      console.warn('Economic calendar fetch error:', e);
    }
  }

  async function fetchHolidayCalendar() {
    try {
      const apiBase = getApiBaseUrl();
      const res = await fetch(`${apiBase}/api/calendar/holidays`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.holidays) {
        state.holidayEvents = data.holidays;
        if (dom.countHolidaysCal) dom.countHolidaysCal.textContent = data.holidays.length;
        renderHolidayCalendar();
      }
    } catch (e) {
      console.warn('Holiday calendar fetch error:', e);
    }
  }

  function renderEconomicCalendar() {
    if (!dom.economicCalendarTbody) return;
    let list = [...(state.economicEvents || [])];

    // Filter by Country
    if (state.calendarCountry && state.calendarCountry !== 'All') {
      const cLow = state.calendarCountry.toLowerCase();
      list = list.filter(e => (e.country || '').toLowerCase().includes(cLow) || (e.country_code || '').toLowerCase() === cLow);
    }

    // Filter by Impact
    if (state.calendarImpact && state.calendarImpact !== 'All') {
      const iLow = state.calendarImpact.toLowerCase();
      list = list.filter(e => (e.impact || '').toLowerCase() === iLow);
    }

    // Search filter
    if (state.calendarSearch && state.calendarSearch.trim()) {
      const sLow = state.calendarSearch.trim().toLowerCase();
      list = list.filter(e => (e.event_name || '').toLowerCase().includes(sLow) || (e.country || '').toLowerCase().includes(sLow));
    }

    if (list.length === 0) {
      dom.economicCalendarTbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--text-dim);">
            <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📊</div>
            <strong>No matching economic calendar events</strong>
            <p style="font-size: 0.8rem; margin-top: 0.25rem;">Try changing country, impact, or search keyword.</p>
          </td>
        </tr>
      `;
      return;
    }

    dom.economicCalendarTbody.innerHTML = list.map(ev => {
      const impactClass = (ev.impact || 'low').toLowerCase();
      const flag = ev.flag || '🌐';
      const searchKey = ev.event_name.split(' ')[0] || ev.country;

      return `
        <tr>
          <td class="cal-cell-datetime">
            <div>${escapeHtml(ev.date || 'Today')}</div>
            <div style="color: var(--text-dim); font-size: 0.72rem;">${escapeHtml(ev.time || '')}</div>
          </td>
          <td>
            <div class="cal-cell-country">
              <span>${flag}</span>
              <span>${escapeHtml(ev.country || '')}</span>
            </div>
          </td>
          <td class="cal-cell-event">${escapeHtml(ev.event_name || '')}</td>
          <td style="text-align: center;">
            <span class="cal-impact-badge ${impactClass}">${escapeHtml(ev.impact || 'Low')}</span>
          </td>
          <td class="cal-cell-num">${escapeHtml(ev.expected || '-')}</td>
          <td class="cal-cell-actual">${escapeHtml(ev.actual || '-')}</td>
          <td class="cal-cell-num" style="color: var(--text-dim);">${escapeHtml(ev.previous || '-')}</td>
          <td style="text-align: center;">
            <button class="cal-action-btn" data-search="${escapeHtml(searchKey)}">
              View News
            </button>
          </td>
        </tr>
      `;
    }).join('');

    dom.economicCalendarTbody.querySelectorAll('.cal-action-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const query = btn.getAttribute('data-search') || '';
        const importantTab = document.getElementById('sourceImportant');
        if (importantTab) {
          importantTab.click();
        }
        dom.searchInput.value = query;
        state.searchQuery = query;
        dom.clearSearchBtn.classList.remove('hidden');
        fetchNews(true);
      });
    });
  }

  function renderHolidayCalendar() {
    if (!dom.holidaysCalendarTbody) return;
    let list = [...(state.holidayEvents || [])];

    if (state.calendarSearch && state.calendarSearch.trim()) {
      const sLow = state.calendarSearch.trim().toLowerCase();
      list = list.filter(h => (h.description || '').toLowerCase().includes(sLow) || (h.date || '').toLowerCase().includes(sLow));
    }

    if (list.length === 0) {
      dom.holidaysCalendarTbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; padding: 2.5rem; color: var(--text-dim);">
            <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🏖️</div>
            <strong>No market holidays found</strong>
          </td>
        </tr>
      `;
      return;
    }

    dom.holidaysCalendarTbody.innerHTML = list.map(h => {
      return `
        <tr>
          <td class="cal-cell-datetime" style="color: #38bdf8; font-weight: 700;">${escapeHtml(h.date || '')}</td>
          <td style="font-weight: 600;">${escapeHtml(h.weekday || '')}</td>
          <td class="cal-cell-event">${escapeHtml(h.description || '')}</td>
          <td style="font-family: var(--font-mono); font-size: 0.75rem;">${escapeHtml(h.exchange || 'NSE / BSE')}</td>
          <td style="text-align: center;">
            <span class="holiday-badge-closed">CLOSED</span>
          </td>
        </tr>
      `;
    }).join('');
  }

  // ---------------------------------------------------------------------------
  // Key Events Module (RBI, Fed, Budget, Holidays, Earnings)
  // ---------------------------------------------------------------------------
  async function fetchKeyEvents() {
    try {
      const apiBase = getApiBaseUrl();
      const res = await fetch(`${apiBase}/api/events`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.events) {
        state.keyEvents = data.events;
        if (dom.countPolicyCal) dom.countPolicyCal.textContent = data.events.length;
        renderKeyEvents();
      }
    } catch (e) {
      console.warn('Key events fetch error:', e);
    }
  }

  function updateKeyEventsBadges() {
    if (dom.countPolicyCal) dom.countPolicyCal.textContent = (state.keyEvents || []).length;
    if (dom.countEconomicCal) dom.countEconomicCal.textContent = (state.economicEvents || []).length;
    if (dom.countHolidaysCal) dom.countHolidaysCal.textContent = (state.holidayEvents || []).length;
  }

  const EVENT_CATEGORY_ICONS = {
    'rbi policy': '🏛️ RBI Policy',
    'fed policy': '🇺🇸 Fed Policy',
    'budget': '💰 Union Budget',
    'market holiday': '🏖️ Market Holiday',
    'earnings': '📊 Earnings Season'
  };

  function getDaysRemainingBadge(eventDateStr) {
    if (!eventDateStr) return '';
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const parts = eventDateStr.split('-').map(Number);
    if (parts.length < 3) return '';
    const [y, m, d] = parts;
    const evDate = new Date(y, m - 1, d);
    evDate.setHours(0, 0, 0, 0);

    const diffDays = Math.round((evDate - today) / (1000 * 60 * 60 * 24));

    if (diffDays < 0) {
      return `<span class="event-countdown-pill countdown-future">Past Event</span>`;
    } else if (diffDays === 0) {
      return `<span class="event-countdown-pill countdown-today">⚡ Today</span>`;
    } else if (diffDays === 1) {
      return `<span class="event-countdown-pill countdown-imminent">⚡ Tomorrow</span>`;
    } else if (diffDays <= 7) {
      return `<span class="event-countdown-pill countdown-imminent">⚡ In ${diffDays} Days</span>`;
    } else if (diffDays <= 30) {
      return `<span class="event-countdown-pill countdown-soon">In ${diffDays} Days</span>`;
    } else {
      const months = Math.round(diffDays / 30);
      return `<span class="event-countdown-pill countdown-future">In ${diffDays} Days (~${months} mo)</span>`;
    }
  }

  function formatEventDate(eventDateStr) {
    if (!eventDateStr) return '';
    try {
      const parts = eventDateStr.split('-').map(Number);
      if (parts.length < 3) return eventDateStr;
      const [y, m, d] = parts;
      const date = new Date(y, m - 1, d);
      return date.toLocaleDateString('en-IN', {
        weekday: 'long',
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      });
    } catch (e) {
      return eventDateStr;
    }
  }

  function renderKeyEvents() {
    if (!dom.eventsGrid) return;
    let list = [...(state.keyEvents || [])];

    if (state.currentEventCountry && state.currentEventCountry !== 'All') {
      list = list.filter(e => (e.country || '').toLowerCase() === state.currentEventCountry.toLowerCase());
    }

    if (list.length === 0) {
      dom.eventsGrid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; padding: 2rem;">
          <div class="empty-icon">📅</div>
          <h3 class="empty-title">No events found</h3>
          <p class="empty-desc">No confirmed events found for this filter category.</p>
        </div>
      `;
      return;
    }

    dom.eventsGrid.innerHTML = list.map(ev => {
      const catKey = (ev.category || '').toLowerCase();
      const catLabel = EVENT_CATEGORY_ICONS[catKey] || `📌 ${escapeHtml(ev.category)}`;
      const countryFlag = (ev.country || '').toLowerCase() === 'india' ? '🇮🇳 India' : '🌐 World';
      const countdownBadge = getDaysRemainingBadge(ev.event_date);
      const formattedDate = formatEventDate(ev.event_date);
      const searchKeyword = ev.event_name.includes('RBI') ? 'RBI' : ev.event_name.includes('Fed') ? 'Fed' : ev.event_name.includes('Budget') ? 'Budget' : ev.event_name;

      return `
        <div class="event-card" data-id="${ev.id}">
          <div class="event-card-top">
            <div class="event-tags-group">
              <span class="event-category-badge">${catLabel}</span>
              <span class="event-country-badge">${countryFlag}</span>
            </div>
            ${countdownBadge}
          </div>

          <h3 class="event-title">${escapeHtml(ev.event_name)}</h3>

          <div class="event-date-row">
            <span>📅 ${escapeHtml(formattedDate)}</span>
          </div>

          <p class="event-desc">${escapeHtml(ev.description || '')}</p>

          <div class="event-card-footer">
            <button class="event-track-btn" data-search="${escapeHtml(searchKeyword)}">
              🔍 Track News Stories
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Attach click listeners to track news stories button
    dom.eventsGrid.querySelectorAll('.event-track-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const query = btn.getAttribute('data-search') || '';
        const importantTab = document.getElementById('sourceImportant');
        if (importantTab) {
          importantTab.click();
        }
        dom.searchInput.value = query;
        state.searchQuery = query;
        dom.clearSearchBtn.classList.remove('hidden');
        fetchNews(true);
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Intelligent Stock Ticker Recognition
  // ---------------------------------------------------------------------------
  const KNOWN_TICKERS = [
    { pattern: /\b(reliance|jio)\b/i, tag: '#RELIANCE' },
    { pattern: /\b(tcs|tata consultancy)\b/i, tag: '#TCS' },
    { pattern: /\b(tata motors|jlr)\b/i, tag: '#TATAMOTORS' },
    { pattern: /\b(tata steel)\b/i, tag: '#TATASTEEL' },
    { pattern: /\b(hdfc|hdfc bank)\b/i, tag: '#HDFCBANK' },
    { pattern: /\b(icici|icici bank)\b/i, tag: '#ICICIBANK' },
    { pattern: /\b(infosys|infy)\b/i, tag: '#INFY' },
    { pattern: /\b(sbi|state bank of india)\b/i, tag: '#SBIN' },
    { pattern: /\b(airtel|bharti airtel)\b/i, tag: '#BHARTIARTL' },
    { pattern: /\b(itc)\b/i, tag: '#ITC' },
    { pattern: /\b(l&t|larsen)\b/i, tag: '#LT' },
    { pattern: /\b(adani|cemindia)\b/i, tag: '#ADANIENT' },
    { pattern: /\b(maruti|suzuki)\b/i, tag: '#MARUTI' },
    { pattern: /\b(wipro)\b/i, tag: '#WIPRO' },
    { pattern: /\b(zomato)\b/i, tag: '#ZOMATO' },
    { pattern: /\b(nvidia|nvda)\b/i, tag: '#NVDA' },
    { pattern: /\b(tesla|tsla)\b/i, tag: '#TSLA' },
    { pattern: /\b(apple|aapl)\b/i, tag: '#AAPL' },
    { pattern: /\b(microsoft|msft)\b/i, tag: '#MSFT' },
    { pattern: /\b(amazon|amzn)\b/i, tag: '#AMZN' },
    { pattern: /\b(google|alphabet)\b/i, tag: '#GOOGL' },
    { pattern: /\b(crude|oil|brent|opec)\b/i, tag: '#CRUDE' },
    { pattern: /\b(gold|bullion)\b/i, tag: '#GOLD' },
    { pattern: /\b(trump|truth social|tariff|tariffs)\b/i, tag: '#TRUMP' }
  ];

  function extractStockTickers(title, desc) {
    const text = `${title} ${desc}`;
    const matched = new Set();
    for (const item of KNOWN_TICKERS) {
      if (item.pattern.test(text)) {
        matched.add(item.tag);
      }
    }
    return Array.from(matched).slice(0, 3);
  }

  // ---------------------------------------------------------------------------
  // Bookmarks Manager
  // ---------------------------------------------------------------------------
  function updateBookmarksBadge() {
    if (dom.badgeBookmarks) {
      dom.badgeBookmarks.textContent = state.bookmarks.length;
    }
  }

  function isBookmarked(link) {
    return state.bookmarks.some(b => b.link === link);
  }

  function toggleBookmark(article) {
    const idx = state.bookmarks.findIndex(b => b.link === article.link);
    if (idx >= 0) {
      state.bookmarks.splice(idx, 1);
      showToast('Removed from Bookmarks', '⭐');
    } else {
      state.bookmarks.unshift(article);
      showToast('Saved to Bookmarks!', '⭐');
    }
    try {
      localStorage.setItem('dalal_bookmarks', JSON.stringify(state.bookmarks));
    } catch (e) {}
    updateBookmarksBadge();

    if (state.currentSource === 'Bookmarks') {
      state.articles = filterArticles(state.bookmarks);
      renderNewsGrid();
    } else {
      updateBookmarkButtonStates();
    }
  }

  function updateBookmarkButtonStates() {
    document.querySelectorAll('.btn-card-bookmark').forEach(btn => {
      const link = decodeURIComponent(btn.getAttribute('data-link'));
      if (isBookmarked(link)) {
        btn.classList.add('starred');
        btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="#f59e0b" stroke="#f59e0b" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>`;
      } else {
        btn.classList.remove('starred');
        btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>`;
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Text-To-Speech Audio Voice Reader
  // ---------------------------------------------------------------------------
  function toggleSpeech(article, cardId) {
    if (!('speechSynthesis' in window)) {
      showToast('Speech Synthesis not supported in this browser.', '⚠️');
      return;
    }

    if (state.speechPlayingId === cardId) {
      window.speechSynthesis.cancel();
      state.speechPlayingId = null;
      resetAudioButtonStates();
      return;
    }

    window.speechSynthesis.cancel();
    state.speechPlayingId = cardId;
    updateAudioButtonStates();

    const cleanTitle = (article.title || '').replace(/[\u{0080}-\u{FFFF}]/gu, '');
    const cleanDesc = (article.description || '').replace(/[\u{0080}-\u{FFFF}]/gu, '');
    const textToSpeak = `${cleanTitle}. ${cleanDesc}`;

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => v.lang.includes('en') && (v.name.includes('Google') || v.name.includes('Natural') || v.name.includes('India') || v.name.includes('US')));
    if (preferredVoice) utterance.voice = preferredVoice;

    utterance.onend = () => {
      state.speechPlayingId = null;
      resetAudioButtonStates();
    };

    utterance.onerror = () => {
      state.speechPlayingId = null;
      resetAudioButtonStates();
    };

    state.speechUtterance = utterance;
    window.speechSynthesis.speak(utterance);
    showToast('Listening to market story...', '🔊');
  }

  function resetAudioButtonStates() {
    document.querySelectorAll('.btn-card-audio').forEach(btn => {
      btn.classList.remove('playing');
      btn.innerHTML = `<span>🔊</span>`;
    });
    if (dom.tldrListenBtn) {
      dom.tldrListenText.textContent = 'Listen to Takeaway';
    }
  }

  function updateAudioButtonStates() {
    document.querySelectorAll('.btn-card-audio').forEach(btn => {
      const cardId = btn.getAttribute('data-id');
      if (cardId === state.speechPlayingId) {
        btn.classList.add('playing');
        btn.innerHTML = `
          <div class="audio-equalizer">
            <span class="equalizer-bar"></span>
            <span class="equalizer-bar"></span>
            <span class="equalizer-bar"></span>
          </div>
        `;
      } else {
        btn.classList.remove('playing');
        btn.innerHTML = `<span>🔊</span>`;
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 3-Bullet Takeaway (TL;DR) Generator & Modal
  // ---------------------------------------------------------------------------
  function generateTldrBullets(article) {
    const title = article.title || '';
    const desc = article.description || '';
    const sentiment = article.sentiment || 'NEUTRAL';
    const source = article.source || 'Market Wire';

    let eventBullet = title;
    let impactBullet = desc.length > 20 ? desc : `Direct corporate announcement filed via ${source}. Expected to influence stock sentiment.`;
    let actionBullet = 'Monitor price volume action at market open; consider support/resistance levels.';

    if (sentiment === 'BULLISH') {
      actionBullet = '🟢 Bullish Trigger: Favorable revenue or strategic expansion could invite strong buying interest.';
    } else if (sentiment === 'BEARISH') {
      actionBullet = '🔴 Bearish Risk: Regulatory scrutiny, tariffs, or profit drop may induce immediate selling pressure.';
    } else if (sentiment === 'EARNINGS') {
      actionBullet = '📊 Earnings Focus: Compare quarterly EBITDA margins and broker target revisions.';
    } else if (sentiment === 'POLICY') {
      actionBullet = '🏛️ Policy & Macro: Interest rate/tariff shift affecting broader sector valuation multiples.';
    }

    return [
      { icon: '🎯', label: 'Key Event', text: eventBullet },
      { icon: '📊', label: 'Financial & Market Impact', text: impactBullet },
      { icon: '💡', label: 'Actionable Takeaway', text: actionBullet }
    ];
  }

  function openTldrModal(article) {
    state.activeModalArticle = article;
    dom.tldrModalTitle.textContent = article.title;
    dom.tldrReadFullBtn.href = article.link;

    const bullets = generateTldrBullets(article);
    dom.tldrBulletsList.innerHTML = bullets.map(b => `
      <div class="tldr-bullet-item">
        <span class="tldr-bullet-icon">${b.icon}</span>
        <div class="tldr-bullet-text">
          <strong>${b.label}:</strong> ${escapeHtml(b.text)}
        </div>
      </div>
    `).join('');

    dom.tldrModalOverlay.classList.remove('hidden');
  }

  function closeTldrModal() {
    dom.tldrModalOverlay.classList.add('hidden');
    if (state.speechPlayingId === 'modal_tldr') {
      window.speechSynthesis.cancel();
      state.speechPlayingId = null;
      dom.tldrListenText.textContent = 'Listen to Takeaway';
    }
  }

  // ---------------------------------------------------------------------------
  // Social Share Modal
  // ---------------------------------------------------------------------------
  function openShareModal(article) {
    state.activeModalArticle = article;
    const sentimentTag = article.sentiment ? `[${article.sentiment}] ` : '';
    const slug = slugify(article.title);
    const storyUrl = `${window.location.origin}/news/${article.id}/${slug}`;
    const shareText = `⚡ ${sentimentTag}${article.title}\n\n📰 Source: ${article.source}\n📊 Full Story: ${storyUrl}\n\nZeroLive – Live Market News, Every Minute`;

    dom.sharePreviewText.textContent = shareText;
    dom.shareWhatsAppBtn.href = `https://api.whatsapp.com/send?text=${encodeURIComponent(shareText)}`;
    dom.shareTelegramBtn.href = `https://t.me/share/url?url=${encodeURIComponent(storyUrl)}&text=${encodeURIComponent(`⚡ ${sentimentTag}${article.title} | Source: ${article.source}`)}`;
    dom.shareCopyLabel.textContent = 'Copy ZeroLive Link';

    dom.shareModalOverlay.classList.remove('hidden');
  }

  function closeShareModal() {
    dom.shareModalOverlay.classList.add('hidden');
  }

  // ---------------------------------------------------------------------------
  // Theme Switching Management (Dark / Light)
  // ---------------------------------------------------------------------------
  function applyTheme(theme) {
    if (theme === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
      if (dom.themeIconDark) dom.themeIconDark.classList.add('hidden');
      if (dom.themeIconLight) dom.themeIconLight.classList.remove('hidden');
    } else {
      document.documentElement.removeAttribute('data-theme');
      if (dom.themeIconDark) dom.themeIconDark.classList.remove('hidden');
      if (dom.themeIconLight) dom.themeIconLight.classList.add('hidden');
    }
  }

  function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    try {
      localStorage.setItem('dalal_theme', newTheme);
    } catch (e) {}
    applyTheme(newTheme);
    showToast(newTheme === 'light' ? 'Switched to Titanium Light Theme ☀️' : 'Switched to Terminal Dark Theme 🌙', '🎨');
  }

  function initTheme() {
    try {
      const savedTheme = localStorage.getItem('dalal_theme');
      if (savedTheme === 'light') {
        applyTheme('light');
      } else {
        applyTheme('dark');
      }
    } catch (e) {
      applyTheme('dark');
    }
  }

  // ---------------------------------------------------------------------------
  // Web Push Notifications (Native VAPID - No Third-Party Accounts)
  // ---------------------------------------------------------------------------
  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function checkPushSubscriptionStatus() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      if (dom.pushToggleBtn) dom.pushToggleBtn.style.display = 'none';
      return;
    }

    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        if (dom.pushToggleBtn) {
          dom.pushToggleBtn.classList.add('active');
          dom.pushLabel.textContent = 'Alerts On';
          dom.pushToggleBtn.title = 'Push alerts active (Click to turn off)';
        }
      } else {
        if (dom.pushToggleBtn) {
          dom.pushToggleBtn.classList.remove('active');
          dom.pushLabel.textContent = 'Alerts';
          dom.pushToggleBtn.title = 'Enable Breaking Market Push Notifications';
        }
      }
    } catch (e) {
      console.warn('Error checking push subscription status:', e);
    }
  }

  async function togglePushNotifications() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      showToast('Web Push is not supported in this browser.', '⚠️');
      return;
    }

    try {
      const reg = await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();

      if (sub) {
        // Unsubscribe
        const endpoint = sub.endpoint;
        await sub.unsubscribe();
        const apiBase = getApiBaseUrl();
        await fetch(`${apiBase}/api/unsubscribe`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ endpoint })
        }).catch(() => {});

        dom.pushToggleBtn.classList.remove('active');
        dom.pushLabel.textContent = 'Alerts';
        showToast('Push notifications disabled.', '🔕');
      } else {
        // Subscribe
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
          showToast('Notification permission was not granted.', '⚠️');
          return;
        }

        const apiBase = getApiBaseUrl();
        const keyResp = await fetch(`${apiBase}/api/push-public-key`);
        if (!keyResp.ok) throw new Error('Failed to fetch VAPID public key');
        const keyData = await keyResp.json();
        const publicKey = keyData.publicKey;

        sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey)
        });

        await fetch(`${apiBase}/api/subscribe`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(sub.toJSON())
        });

        dom.pushToggleBtn.classList.add('active');
        dom.pushLabel.textContent = 'Alerts On';
        showToast('🔔 Breaking news push alerts activated! Test alert incoming...', '✅');

        // Send a real test push notification
        setTimeout(() => {
          fetch(`${apiBase}/api/send-test-push`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subscription: sub.toJSON() })
          }).catch(() => {});
        }, 1000);
      }
    } catch (err) {
      console.error('Error toggling push notifications:', err);
      showToast('Push setup error. Ensure notifications are allowed in browser.', '⚠️');
    }
  }

  // ---------------------------------------------------------------------------
  // Data Fetching & API Communication
  // ---------------------------------------------------------------------------
  const MACRO_EVENT_PATTERN = /\b(rbi|fed|federal reserve|repo rate|interest rate|rate cut|rate hike|rate decision|fomc|ecb|boj|boe|inflation|cpi|wpi|gdp|monetary policy|mpc|fiscal deficit|forex reserves|tariff|tariffs|budget)\b/i;

  function filterArticles(list) {
    let filtered = [...list];
    if (state.currentSentiment && state.currentSentiment !== 'All') {
      if (state.currentSentiment === 'MACRO_EVENTS') {
        filtered = filtered.filter(a =>
          MACRO_EVENT_PATTERN.test(a.title || '') ||
          MACRO_EVENT_PATTERN.test(a.description || '') ||
          a.category === 'POLICY' ||
          a.sentiment === 'POLICY'
        );
      } else {
        filtered = filtered.filter(a => a.sentiment === state.currentSentiment);
      }
    }
    if (state.searchQuery && state.searchQuery.trim()) {
      const q = state.searchQuery.trim().toLowerCase();
      filtered = filtered.filter(a =>
        (a.title && a.title.toLowerCase().includes(q)) ||
        (a.description && a.description.toLowerCase().includes(q))
      );
    }
    return filtered;
  }

  function getApiBaseUrl() {
    // Live production API uses relative path by default
    // Only attempt http://localhost:8000 if developing locally on localhost or 127.0.0.1
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return window.location.port === '8000' ? '' : 'http://localhost:8000';
    }
    // Public visitors never try to ping localhost
    return '';
  }

  async function fetchNews(showSpinner = false) {
    if (state.currentType === 'events') {
      if (dom.eventsWrapper) dom.eventsWrapper.classList.remove('hidden');
      if (dom.feedWrapper) dom.feedWrapper.classList.add('hidden');
      if (dom.filterActionsBar) dom.filterActionsBar.classList.add('hidden');
      if (dom.activeQueryBar) dom.activeQueryBar.classList.add('hidden');
      dom.refreshBtn.classList.remove('spinning');
      await Promise.all([fetchEconomicCalendar(), fetchHolidayCalendar(), fetchKeyEvents()]);
      return;
    } else {
      if (dom.eventsWrapper) dom.eventsWrapper.classList.add('hidden');
      if (dom.feedWrapper) dom.feedWrapper.classList.remove('hidden');
      if (dom.filterActionsBar) dom.filterActionsBar.classList.remove('hidden');
    }

    if (showSpinner) {
      dom.refreshBtn.classList.add('spinning');
      dom.skeletonGrid.classList.remove('hidden');
      dom.newsGrid.classList.add('hidden');
      dom.emptyState.classList.add('hidden');
    }

    try {
      const apiBase = getApiBaseUrl();
      const params = new URLSearchParams();
      if (state.currentType && state.currentType !== 'all') {
        params.append('type', state.currentType);
      }
      if (state.currentSource && state.currentSource.toLowerCase() !== 'all') {
        params.append('source', state.currentSource);
      }
      if (state.currentSentiment && state.currentSentiment !== 'All') {
        params.append('sentiment', state.currentSentiment);
      }
      if (state.searchQuery && state.searchQuery.trim()) {
        params.append('search', state.searchQuery.trim());
      }
      params.append('limit', '100');

      const newsPromise = fetch(`${apiBase}/api/news?${params.toString()}`);
      const statsPromise = fetch(`${apiBase}/api/stats`);

      const [newsResponse, statsResponse] = await Promise.all([
        newsPromise,
        statsPromise.catch(() => null)
      ]);

      if (!newsResponse.ok) {
        throw new Error(`Server returned HTTP ${newsResponse.status}`);
      }

      const newsData = await newsResponse.json();
      const statsData = statsResponse && statsResponse.ok ? await statsResponse.json() : null;

      state.articles = newsData.articles || [];
      state.stats = statsData ? statsData.stats : null;
      state.lastFetchedAt = new Date();
      state.connectionFailureCount = 0;

      if (dom.connectionBanner) {
        dom.connectionBanner.classList.add('hidden');
        dom.connectionBanner.innerHTML = '';
      }

      updateStatsDisplay();
      updateLastUpdatedLabel();

      // Safely render cards
      try {
        renderNewsGrid();
      } catch (renderErr) {
        console.error('Error rendering cards:', renderErr);
      }

      // Reset auto-refresh countdown
      state.secondsRemaining = state.autoRefreshIntervalSec;
      updateCountdownDisplay();

    } catch (err) {
      state.connectionFailureCount = (state.connectionFailureCount || 0) + 1;
      console.warn(`News sync connection issue (attempt ${state.connectionFailureCount}):`, err);

      // Render clean user banner ONLY after 2 failed retries
      if (state.connectionFailureCount >= 2 && dom.connectionBanner) {
        dom.connectionBanner.innerHTML = `
          <div class="banner-content">
            <span class="banner-icon">⚡</span>
            <div class="banner-text">
              <strong>⚡ Live feed syncing...</strong> Reconnecting to market server.
            </div>
          </div>
          <button class="banner-retry-btn" id="bannerRetryBtn">Retry</button>
        `;
        dom.connectionBanner.classList.remove('hidden');
      }

      if (!state.articles || state.articles.length === 0) {
        dom.newsGrid.classList.add('hidden');
        dom.emptyState.classList.add('hidden');
      }
      if (showSpinner) {
        showToast('⚡ Live feed syncing... Reconnecting to market server.', '⚡');
      }
    } finally {
      dom.refreshBtn.classList.remove('spinning');
      dom.skeletonGrid.classList.add('hidden');
    }
  }

  async function triggerManualRefresh() {
    dom.refreshBtn.classList.add('spinning');
    showToast('Checking Indian market feeds & exchange filings...', '📡');

    try {
      const apiBase = getApiBaseUrl();
      await fetch(`${apiBase}/api/refresh`, { method: 'POST' });
      setTimeout(() => {
        fetchNews(true);
        showToast('Feed refreshed with latest market stories!', '✅');
      }, 1500);
    } catch (err) {
      fetchNews(true);
    }
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  function updateStatsDisplay() {
    if (!state.stats) return;

    dom.statTotalArticles.textContent = state.stats.total_articles || '0';
    dom.statBullishCount.textContent = state.stats.sentiments?.BULLISH || '0';
    dom.statBearishCount.textContent = state.stats.sentiments?.BEARISH || '0';

    // Calculate source badges
    const sources = state.stats.sources || {};
    let etTotal = 0;
    let bsTotal = 0;
    let mintTotal = 0;
    let mcTotal = 0;
    let nseTotal = 0;
    let bseTotal = 0;
    let internationalTotal = 0;
    let trumpTotal = 0;

    for (const [srcName, count] of Object.entries(sources)) {
      const lower = srcName.toLowerCase();
      if (lower.includes('economic times')) etTotal += count;
      else if (lower.includes('business standard')) bsTotal += count;
      else if (lower.includes('livemint') || lower.includes('mint')) mintTotal += count;
      else if (lower.includes('moneycontrol')) mcTotal += count;
      else if (lower.includes('nse')) nseTotal += count;
      else if (lower.includes('bse')) bseTotal += count;
      else if (lower.includes('trump')) trumpTotal += count;
      else if (lower.includes('reuters') || lower.includes('yahoo') || lower.includes('cnbc') || lower.includes('bloomberg') || lower.includes('investing') || lower.includes('financial times') || lower.includes('ft')) {
        internationalTotal += count;
      }
    }

    if (dom.badgeImportant) dom.badgeImportant.textContent = state.stats.types?.important || '0';
    if (dom.badgeAll) dom.badgeAll.textContent = state.stats.total_articles || '0';
    if (dom.badgeFilings) dom.badgeFilings.textContent = state.stats.types?.filing || (nseTotal + bseTotal);
    if (dom.badgeExchange) dom.badgeExchange.textContent = (nseTotal + bseTotal);
    if (dom.badgeIndian) dom.badgeIndian.textContent = (etTotal + bsTotal + mintTotal + mcTotal);
    if (dom.badgeInternational) dom.badgeInternational.textContent = internationalTotal;
    if (dom.badgeTrump) dom.badgeTrump.textContent = trumpTotal;
  }

  function getSourceClass(sourceName) {
    if (!sourceName) return 'source-default';
    const lower = sourceName.toLowerCase();
    if (lower.includes('nse')) return 'source-nse';
    if (lower.includes('bse')) return 'source-bse';
    if (lower.includes('economic times')) return 'source-et';
    if (lower.includes('business standard')) return 'source-bs';
    if (lower.includes('livemint') || lower.includes('mint')) return 'source-livemint';
    if (lower.includes('moneycontrol')) return 'source-mc';
    if (lower.includes('reuters')) return 'source-reuters';
    if (lower.includes('yahoo')) return 'source-yahoo';
    if (lower.includes('cnbc')) return 'source-cnbc';
    if (lower.includes('trump')) return 'source-trump';
    return 'source-default';
  }

  function getSentimentBadge(sentiment) {
    if (!sentiment || sentiment === 'NEUTRAL') return '';
    const map = {
      'BULLISH': '<span class="badge-sentiment BULLISH">🟢 BULLISH</span>',
      'BEARISH': '<span class="badge-sentiment BEARISH">🔴 BEARISH</span>',
      'EARNINGS': '<span class="badge-sentiment EARNINGS">📊 EARNINGS</span>',
      'POLICY': '<span class="badge-sentiment POLICY">🏛️ RBI/POLICY</span>'
    };
    return map[sentiment] || '';
  }

  function slugify(text) {
    if (!text) return 'market-news';
    return text.toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .trim()
      .replace(/[\s-]+/g, '-')
      .slice(0, 80) || 'market-news';
  }

  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function renderNewsGrid() {
    let articles = state.articles;

    if (state.currentSource === 'Bookmarks') {
      articles = filterArticles(state.bookmarks);
    }

    if (!articles || articles.length === 0) {
      dom.newsGrid.classList.add('hidden');
      dom.emptyState.classList.remove('hidden');
      updateActiveQueryBar();
      return;
    }

    dom.emptyState.classList.add('hidden');
    dom.newsGrid.classList.remove('hidden');

    const html = articles.map((art, index) => {
      const sourceClass = getSourceClass(art.source);
      const sentimentBadge = getSentimentBadge(art.sentiment);
      const relativeTime = formatRelativeTime(art.published_at);
      const exactTime = art.published_str || new Date(art.published_at).toLocaleString();
      const escapedTitle = escapeHtml(art.title);
      const escapedDesc = escapeHtml(art.description || 'Click to view the complete official filing and market analysis.');
      const feedLabel = art.feed_name || art.source || 'Market Update';
      const isPdf = art.link && (art.link.toLowerCase().endsWith('.pdf') || art.link.includes('AttachLive') || art.link.includes('nsearchives'));
      const isExchange = art.source && (art.source.includes('NSE') || art.source.includes('BSE'));
      const isStarred = isBookmarked(art.link);
      const cardId = `art_${index}_${Math.abs(art.title.length * 31)}`;

      const artSlug = slugify(art.title);
      const onSiteUrl = `/news/${art.id}/${artSlug}`;

      let linkText = 'Read Story';
      let targetHref = onSiteUrl;
      let targetAttr = '';
      if (isPdf) {
        linkText = 'View Official PDF Filing ↗';
        targetHref = encodeURI(art.link);
        targetAttr = 'target="_blank" rel="noopener noreferrer"';
      } else if (isExchange) {
        linkText = 'Read Filing on ZeroLive';
      }

      const tickers = extractStockTickers(art.title, art.description || '');
      const tickerBadges = tickers.map(t => `<button class="ticker-tag" data-tag="${t.replace('#', '')}">${t}</button>`).join('');

      return `
        <article class="news-card sentiment-${art.sentiment || 'NEUTRAL'}" data-index="${index}" data-link="${encodeURIComponent(art.link)}">
          <header class="card-header">
            <div class="card-badges">
              <span class="badge-source ${sourceClass}">${escapeHtml(feedLabel)}</span>
              ${sentimentBadge}
            </div>
            <time class="card-time" title="${escapeHtml(exactTime)}" datetime="${art.published_at}">
              ${relativeTime}
            </time>
          </header>

          <div class="card-body">
            ${tickers.length > 0 ? `<div class="card-tickers">${tickerBadges}</div>` : ''}
            <h3 class="card-title">
              <a href="${targetHref}" ${targetAttr}>
                ${escapedTitle}
              </a>
            </h3>
            ${escapedDesc ? `<p class="card-description">${escapedDesc}</p>` : ''}
          </div>

          <footer class="card-footer">
            <a href="${targetHref}" ${targetAttr} class="card-link-out ${isPdf ? 'link-pdf' : ''}">
              ${linkText}
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"></line>
                <polyline points="12 5 19 12 12 19"></polyline>
              </svg>
            </a>
            <div class="card-actions">
              <!-- Listen Voice Reader -->
              <button class="btn-card-action btn-card-audio" data-id="${cardId}" data-index="${index}" title="Listen to news" aria-label="Listen">
                <span>🔊</span>
              </button>

              <!-- 3-Bullet TL;DR Takeaway -->
              <button class="btn-card-action btn-card-tldr" data-index="${index}" title="3-Bullet Instant Takeaway" aria-label="Instant Takeaway">
                <span>⚡</span>
              </button>

              <!-- Star / Bookmark -->
              <button class="btn-card-action btn-card-bookmark ${isStarred ? 'starred' : ''}" data-index="${index}" data-link="${encodeURIComponent(art.link)}" title="Save to Bookmarks" aria-label="Bookmark">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="${isStarred ? '#f59e0b' : 'none'}" stroke="${isStarred ? '#f59e0b' : 'currentColor'}" stroke-width="2">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                </svg>
              </button>

              <!-- 1-Click WhatsApp / Telegram Share -->
              <button class="btn-card-action btn-card-share" data-index="${index}" title="Share to WhatsApp / Telegram" aria-label="Share">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="18" cy="5" r="3"></circle>
                  <circle cx="6" cy="12" r="3"></circle>
                  <circle cx="18" cy="19" r="3"></circle>
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                </svg>
              </button>
            </div>
          </footer>
        </article>
      `;
    }).join('');

    dom.newsGrid.innerHTML = html;
    updateActiveQueryBar();
    attachCardListeners();
  }

  function updateActiveQueryBar() {
    const hasFilter = (state.currentSource !== 'All') || (state.currentSentiment !== 'All') || (state.searchQuery.trim() !== '');

    if (hasFilter) {
      dom.activeQueryBar.classList.remove('hidden');
      const parts = [];
      if (state.currentSource !== 'All') parts.push(`Source: ${state.currentSource}`);
      if (state.currentSentiment !== 'All') parts.push(`Signal: ${state.currentSentiment}`);
      if (state.searchQuery.trim()) parts.push(`Search: "${state.searchQuery.trim()}"`);
      dom.activeQueryText.textContent = `Active Filters: ${parts.join(' • ')} (${state.articles.length} results)`;
    } else {
      dom.activeQueryBar.classList.add('hidden');
    }
  }

  function attachCardListeners() {
    // 1. Clickable Ticker Tags
    dom.newsGrid.querySelectorAll('.ticker-tag').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const tag = btn.getAttribute('data-tag');
        dom.searchInput.value = tag;
        state.searchQuery = tag;
        dom.clearSearchBtn.classList.remove('hidden');
        fetchNews(true);
      });
    });

    // 2. Audio Voice Reader Button
    dom.newsGrid.querySelectorAll('.btn-card-audio').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-index'), 10);
        const cardId = btn.getAttribute('data-id');
        const art = state.currentSource === 'Bookmarks' ? state.bookmarks[idx] : state.articles[idx];
        if (art) toggleSpeech(art, cardId);
      });
    });

    // 3. 3-Bullet TL;DR Takeaway Button
    dom.newsGrid.querySelectorAll('.btn-card-tldr').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-index'), 10);
        const art = state.currentSource === 'Bookmarks' ? state.bookmarks[idx] : state.articles[idx];
        if (art) openTldrModal(art);
      });
    });

    // 4. Bookmark Button
    dom.newsGrid.querySelectorAll('.btn-card-bookmark').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-index'), 10);
        const art = state.currentSource === 'Bookmarks' ? state.bookmarks[idx] : state.articles[idx];
        if (art) toggleBookmark(art);
      });
    });

    // 5. Share Button
    dom.newsGrid.querySelectorAll('.btn-card-share').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-index'), 10);
        const art = state.currentSource === 'Bookmarks' ? state.bookmarks[idx] : state.articles[idx];
        if (art) openShareModal(art);
      });
    });
  }

  function updateLastUpdatedLabel() {
    if (!state.lastFetchedAt) return;
    dom.lastUpdatedTime.textContent = formatTimeOnly(state.lastFetchedAt);
  }

  function updateCountdownDisplay() {
    const minutes = Math.floor(state.secondsRemaining / 60);
    const seconds = state.secondsRemaining % 60;
    const str = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    dom.autoRefreshCountdown.textContent = str;
  }

  // ---------------------------------------------------------------------------
  // Event Listeners & Interactions
  // ---------------------------------------------------------------------------

  function setupEventListeners() {
    // Refresh Button Click
    dom.refreshBtn.addEventListener('click', () => {
      triggerManualRefresh();
    });

    // Helper to deactivate all tabs and tab groups
    function deactivateAllSourceTabs() {
      dom.sourceTabs.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      dom.sourceTabGroups.forEach(g => {
        g.classList.remove('active-parent');
        g.classList.remove('menu-open');
      });
      if (dom.dropdownBackdrop) dom.dropdownBackdrop.classList.add('hidden');
    }

    // Helper to close dropdowns without unselecting active tab
    function closeAllDropdowns() {
      dom.sourceTabGroups.forEach(g => g.classList.remove('menu-open'));
      if (dom.dropdownBackdrop) dom.dropdownBackdrop.classList.add('hidden');
    }

    // Source Tabs Click (Main Hubs & Standalone Tabs)
    dom.sourceTabs.forEach(tab => {
      tab.addEventListener('click', (e) => {
        e.stopPropagation();
        deactivateAllSourceTabs();

        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');

        const parentGroup = tab.closest('.source-tab-group');
        if (parentGroup) {
          parentGroup.classList.add('active-parent');
          const firstItem = parentGroup.querySelector('.dropdown-item');
          parentGroup.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('active'));
          if (firstItem) firstItem.classList.add('active');
        }

        state.currentType = tab.getAttribute('data-type') || 'all';
        state.currentSource = tab.getAttribute('data-source') || 'All';
        fetchNews(true);
      });
    });

    // Dropdown Triggers (▾ Arrow)
    dom.dropdownTriggers.forEach(trigger => {
      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        const parentGroup = trigger.closest('.source-tab-group');
        if (!parentGroup) return;

        const isCurrentlyOpen = parentGroup.classList.contains('menu-open');
        closeAllDropdowns();

        if (!isCurrentlyOpen) {
          parentGroup.classList.add('menu-open');
          if (dom.dropdownBackdrop) dom.dropdownBackdrop.classList.remove('hidden');
        }
      });
    });

    // Dropdown Items Click (e.g. Moneycontrol, LiveMint, NSE)
    dom.dropdownItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        const parentGroup = item.closest('.source-tab-group');
        deactivateAllSourceTabs();

        if (parentGroup) {
          parentGroup.classList.add('active-parent');
          const groupTab = parentGroup.querySelector('.source-tab');
          if (groupTab) {
            groupTab.classList.add('active');
            groupTab.setAttribute('aria-selected', 'true');
          }
          parentGroup.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('active'));
          item.classList.add('active');
        }

        closeAllDropdowns();
        state.currentType = item.getAttribute('data-type') || 'all';
        state.currentSource = item.getAttribute('data-source') || 'All';
        showToast(`Filtered by ${item.textContent.trim()}`, '🔍');
        fetchNews(true);
      });
    });

    // Close buttons inside mobile dropdown headers
    document.querySelectorAll('.menu-close-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeAllDropdowns();
      });
    });

    // Backdrop click closes dropdowns
    if (dom.dropdownBackdrop) {
      dom.dropdownBackdrop.addEventListener('click', closeAllDropdowns);
    }

    // Close dropdowns when clicking anywhere outside
    document.addEventListener('click', closeAllDropdowns);

    // Sentiment Pills Click
    dom.sentimentPills.forEach(pill => {
      pill.addEventListener('click', () => {
        dom.sentimentPills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');

        state.currentSentiment = pill.getAttribute('data-sentiment');
        fetchNews(true);
      });
    });

    // Instant Search Input
    dom.searchInput.addEventListener('input', (e) => {
      const val = e.target.value;
      state.searchQuery = val;

      if (val.length > 0) {
        dom.clearSearchBtn.classList.remove('hidden');
      } else {
        dom.clearSearchBtn.classList.add('hidden');
      }

      clearTimeout(state.searchDebounceTimer);
      state.searchDebounceTimer = setTimeout(() => {
        fetchNews(false);
      }, 250);
    });

    // Clear Search Button
    dom.clearSearchBtn.addEventListener('click', () => {
      dom.searchInput.value = '';
      state.searchQuery = '';
      dom.clearSearchBtn.classList.add('hidden');
      fetchNews(false);
    });

    // Reset Filter Buttons
    const resetAll = () => {
      state.currentSource = 'All';
      state.currentSentiment = 'All';
      state.searchQuery = '';
      dom.searchInput.value = '';
      dom.clearSearchBtn.classList.add('hidden');

      deactivateAllSourceTabs();
      const allTab = document.getElementById('sourceAll');
      if (allTab) {
        allTab.classList.add('active');
        allTab.setAttribute('aria-selected', 'true');
      }

      dom.sentimentPills.forEach(p => {
        p.classList.toggle('active', p.getAttribute('data-sentiment') === 'All');
      });

      fetchNews(true);
    };

    if (dom.resetFiltersBtn) dom.resetFiltersBtn.addEventListener('click', resetAll);
    if (dom.connectionBanner) {
      dom.connectionBanner.addEventListener('click', (e) => {
        if (e.target && (e.target.id === 'bannerRetryBtn' || e.target.classList.contains('banner-retry-btn'))) {
          fetchNews(true);
        }
      });
    }
    if (dom.themeToggleBtn) dom.themeToggleBtn.addEventListener('click', toggleTheme);
    if (dom.pushToggleBtn) dom.pushToggleBtn.addEventListener('click', togglePushNotifications);

    // Modal Close buttons
    if (dom.tldrModalCloseBtn) dom.tldrModalCloseBtn.addEventListener('click', closeTldrModal);
    if (dom.tldrModalOverlay) {
      dom.tldrModalOverlay.addEventListener('click', (e) => {
        if (e.target === dom.tldrModalOverlay) closeTldrModal();
      });
    }

    if (dom.shareModalCloseBtn) dom.shareModalCloseBtn.addEventListener('click', closeShareModal);
    if (dom.shareModalOverlay) {
      dom.shareModalOverlay.addEventListener('click', (e) => {
        if (e.target === dom.shareModalOverlay) closeShareModal();
      });
    }

    // Modal Listen Button
    if (dom.tldrListenBtn) {
      dom.tldrListenBtn.addEventListener('click', () => {
        if (!state.activeModalArticle) return;
        const bullets = generateTldrBullets(state.activeModalArticle);
        const text = bullets.map(b => `${b.label}. ${b.text}`).join('. ');
        toggleSpeech({ title: state.activeModalArticle.title, description: text }, 'modal_tldr');
        dom.tldrListenText.textContent = state.speechPlayingId ? 'Stop Listening' : 'Listen to Takeaway';
      });
    }

    // Copy Share Alert Link
    if (dom.shareCopyLinkBtn) {
      dom.shareCopyLinkBtn.addEventListener('click', () => {
        if (!state.activeModalArticle) return;
        const sentimentTag = state.activeModalArticle.sentiment ? `[${state.activeModalArticle.sentiment}] ` : '';
        const slug = slugify(state.activeModalArticle.title);
        const storyUrl = `${window.location.origin}/news/${state.activeModalArticle.id}/${slug}`;
        const text = `⚡ ${sentimentTag}${state.activeModalArticle.title}\n\n📰 Source: ${state.activeModalArticle.source}\n📊 Full Story: ${storyUrl}\n\nZeroLive – Live Market News, Every Minute`;
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(() => {
            dom.shareCopyLabel.textContent = '✅ Copied to Clipboard!';
            showToast('ZeroLive story link copied to clipboard!', '📋');
            setTimeout(() => {
              if (dom.shareCopyLabel) dom.shareCopyLabel.textContent = 'Copy ZeroLive Link';
            }, 2000);
          });
        }
      });
    }

    // Calendar Sub-Tab Switcher (Economic / Holidays / Policy)
    dom.calendarSubtabs.forEach(tab => {
      tab.addEventListener('click', () => {
        dom.calendarSubtabs.forEach(t => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        state.currentCalendarSubtab = tab.getAttribute('data-subtab') || 'economic';

        if (state.currentCalendarSubtab === 'economic') {
          if (dom.paneEconomic) dom.paneEconomic.classList.remove('hidden');
          if (dom.paneHolidays) dom.paneHolidays.classList.add('hidden');
          if (dom.panePolicy) dom.panePolicy.classList.add('hidden');
          if (dom.calendarControlsBar) dom.calendarControlsBar.classList.remove('hidden');
          renderEconomicCalendar();
        } else if (state.currentCalendarSubtab === 'holidays') {
          if (dom.paneEconomic) dom.paneEconomic.classList.add('hidden');
          if (dom.paneHolidays) dom.paneHolidays.classList.remove('hidden');
          if (dom.panePolicy) dom.panePolicy.classList.add('hidden');
          if (dom.calendarControlsBar) dom.calendarControlsBar.classList.remove('hidden');
          renderHolidayCalendar();
        } else if (state.currentCalendarSubtab === 'policy') {
          if (dom.paneEconomic) dom.paneEconomic.classList.add('hidden');
          if (dom.paneHolidays) dom.paneHolidays.classList.add('hidden');
          if (dom.panePolicy) dom.panePolicy.classList.remove('hidden');
          renderKeyEvents();
        }
      });
    });

    // Calendar Filters (Country & Impact & Search)
    if (dom.calendarCountryFilter) {
      dom.calendarCountryFilter.addEventListener('change', (e) => {
        state.calendarCountry = e.target.value;
        renderEconomicCalendar();
      });
    }

    if (dom.calendarImpactFilter) {
      dom.calendarImpactFilter.addEventListener('change', (e) => {
        state.calendarImpact = e.target.value;
        renderEconomicCalendar();
      });
    }

    if (dom.calendarSearchInput) {
      dom.calendarSearchInput.addEventListener('input', (e) => {
        state.calendarSearch = e.target.value;
        if (state.currentCalendarSubtab === 'economic') {
          renderEconomicCalendar();
        } else if (state.currentCalendarSubtab === 'holidays') {
          renderHolidayCalendar();
        }
      });
    }

    // Event Filter Chips (All / India / World)
    document.querySelectorAll('.event-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.event-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.currentEventCountry = chip.getAttribute('data-country') || 'All';
        renderKeyEvents();
      });
    });

    // Back to top floating button
    window.addEventListener('scroll', () => {
      if (window.scrollY > 400) {
        dom.backToTopBtn.classList.remove('hidden');
      } else {
        dom.backToTopBtn.classList.add('hidden');
      }
    });

    dom.backToTopBtn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // Tick Interval: Every 1 second
    setInterval(() => {
      updateLiveClock();
      updateMarketStatus();
      state.secondsRemaining--;
      if (state.secondsRemaining <= 0) {
        state.secondsRemaining = state.autoRefreshIntervalSec;
        fetchNews(false);
      }
      updateCountdownDisplay();
    }, 1000);

    // Refresh Market Indices every 60 seconds
    setInterval(() => {
      fetchMarketIndices();
    }, 60000);
  }

  // ---------------------------------------------------------------------------
  // PWA Install Prompt & Standalone Mode Detection
  // ---------------------------------------------------------------------------
  let deferredInstallPrompt = null;

  function isRunningStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
           (window.navigator && window.navigator.standalone === true);
  }

  function initPwaInstall() {
    // If already running as installed standalone PWA, hide install button
    if (isRunningStandalone()) {
      document.body.classList.add('pwa-installed');
      if (dom.installPwaBtn) dom.installPwaBtn.style.display = 'none';
      return;
    }

    // Capture Chrome/Android beforeinstallprompt event
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredInstallPrompt = e;
      if (dom.installPwaBtn) {
        dom.installPwaBtn.style.display = 'inline-flex';
      }
    });

    window.addEventListener('appinstalled', () => {
      deferredInstallPrompt = null;
      document.body.classList.add('pwa-installed');
      if (dom.installPwaBtn) dom.installPwaBtn.style.display = 'none';
      showToast('ZeroLive app installed to your Home Screen! 📲', '✅');
    });

    if (dom.installPwaBtn) {
      dom.installPwaBtn.addEventListener('click', handleInstallClick);
    }
    if (dom.installModalCloseBtn) {
      dom.installModalCloseBtn.addEventListener('click', closeInstallModal);
    }
    if (dom.installModalDismissBtn) {
      dom.installModalDismissBtn.addEventListener('click', closeInstallModal);
    }
    if (dom.installModalOverlay) {
      dom.installModalOverlay.addEventListener('click', (e) => {
        if (e.target === dom.installModalOverlay) closeInstallModal();
      });
    }
  }

  async function handleInstallClick() {
    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      const { outcome } = await deferredInstallPrompt.userChoice;
      if (outcome === 'accepted') {
        if (dom.installPwaBtn) dom.installPwaBtn.style.display = 'none';
        showToast('Installing ZeroLive... 📲', '⏳');
      }
      deferredInstallPrompt = null;
    } else {
      openInstallModal();
    }
  }

  function openInstallModal() {
    if (!dom.installModalOverlay) return;
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    if (dom.iosInstallGuide && dom.generalInstallGuide) {
      if (isIOS) {
        dom.iosInstallGuide.style.display = 'block';
        dom.generalInstallGuide.style.display = 'none';
      } else {
        dom.iosInstallGuide.style.display = 'none';
        dom.generalInstallGuide.style.display = 'block';
      }
    }
    dom.installModalOverlay.classList.remove('hidden');
  }

  function closeInstallModal() {
    if (dom.installModalOverlay) dom.installModalOverlay.classList.add('hidden');
  }

  // ---------------------------------------------------------------------------
  // App Initialization
  // ---------------------------------------------------------------------------
  function init() {
    initTheme();
    initPwaInstall();
    updateLiveClock();
    updateMarketStatus();
    setupEventListeners();
    updateBookmarksBadge();
    fetchMarketIndices();
    fetchKeyEvents();
    fetchEconomicCalendar();
    fetchHolidayCalendar();
    checkPushSubscriptionStatus();
    fetchNews(true);
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
