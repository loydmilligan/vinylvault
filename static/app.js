/**
 * VinylVault - Touch-Optimized JavaScript
 * Vanilla JavaScript with touch gestures, animations, and Pi optimizations
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        TOUCH_THRESHOLD: 50,
        SWIPE_THRESHOLD: 100,
        SWIPE_VELOCITY_THRESHOLD: 0.3,
        ANIMATION_DURATION: 250,
        SCROLL_DEBOUNCE: 16,
        SEARCH_DEBOUNCE: 300,
        INTERSECTION_THRESHOLD: 0.1,
        VINYL_SPIN_DURATION: 2000,
        PRELOAD_BATCH_SIZE: 10,
        CACHE_RETRY_DELAY: 1000
    };

    // Application state
    const state = {
        isTouch: false,
        touchStartX: 0,
        touchStartY: 0,
        touchStartTime: 0,
        pullRefreshStartY: 0,
        isPullRefreshing: false,
        searchTimeout: null,
        intersectionObserver: null,
        currentPage: 1,
        isLoading: false,
        imageCache: new Map(),
        preloadQueue: [],
        isPreloading: false
    };

    // DOM elements cache
    const elements = {
        body: document.body,
        header: null,
        searchInput: null,
        randomButton: null,
        albumGrid: null,
        pagination: null,
        pullRefreshIndicator: null
    };

    /**
     * Initialize the application
     */
    function init() {
        // Cache DOM elements
        cacheElements();
        
        // Detect touch device
        detectTouchDevice();
        
        // Setup touch optimizations
        setupTouchOptimizations();
        
        // Setup event listeners
        setupEventListeners();
        
        // Initialize components
        initializeComponents();
        
        // Setup intersection observer for lazy loading
        setupIntersectionObserver();
        
        console.log('VinylVault initialized');
    }

    /**
     * Cache frequently used DOM elements
     */
    function cacheElements() {
        elements.header = document.querySelector('.header');
        elements.searchInput = document.querySelector('.search-input');
        elements.randomButton = document.querySelector('a[href*="random"]');
        elements.albumGrid = document.querySelector('.album-grid');
        elements.pagination = document.querySelector('.pagination');
    }

    /**
     * Detect if device supports touch
     */
    function detectTouchDevice() {
        state.isTouch = 'ontouchstart' in window || 
                       navigator.maxTouchPoints > 0 || 
                       navigator.msMaxTouchPoints > 0;
        
        if (state.isTouch) {
            elements.body.classList.add('touch-device');
        }
    }

    /**
     * Setup touch-specific optimizations
     */
    function setupTouchOptimizations() {
        // Disable 300ms click delay
        if (state.isTouch) {
            const meta = document.createElement('meta');
            meta.name = 'viewport';
            meta.content = 'width=device-width, initial-scale=1.0, user-scalable=no, shrink-to-fit=no';
            
            const existingMeta = document.querySelector('meta[name="viewport"]');
            if (existingMeta) {
                existingMeta.parentNode.replaceChild(meta, existingMeta);
            } else {
                document.head.appendChild(meta);
            }
        }

        // Prevent zoom on double tap
        let lastTouchEnd = 0;
        document.addEventListener('touchend', function(event) {
            const now = (new Date()).getTime();
            if (now - lastTouchEnd <= 300) {
                event.preventDefault();
            }
            lastTouchEnd = now;
        }, false);

        // Prevent overscroll
        document.addEventListener('touchmove', function(e) {
            if (e.target.closest('.touch-scroll')) return;
            
            const target = e.target;
            const isScrollable = target.scrollHeight > target.clientHeight;
            
            if (!isScrollable) {
                e.preventDefault();
            }
        }, { passive: false });
    }

    /**
     * Setup all event listeners
     */
    function setupEventListeners() {
        // Touch events
        if (state.isTouch) {
            setupTouchEvents();
        }

        // Search functionality
        if (elements.searchInput) {
            setupSearchEvents();
        }

        // Random button
        if (elements.randomButton) {
            setupRandomButton();
        }

        // Album grid events
        if (elements.albumGrid) {
            setupAlbumGridEvents();
        }

        // Keyboard shortcuts
        setupKeyboardEvents();

        // Window events
        setupWindowEvents();

        // Pull to refresh
        setupPullToRefresh();
    }

    /**
     * Setup touch event handlers
     */
    function setupTouchEvents() {
        // Touch start
        document.addEventListener('touchstart', handleTouchStart, { passive: true });
        
        // Touch move
        document.addEventListener('touchmove', handleTouchMove, { passive: false });
        
        // Touch end
        document.addEventListener('touchend', handleTouchEnd, { passive: true });

        // Prevent context menu on long press
        document.addEventListener('contextmenu', function(e) {
            if (state.isTouch) {
                e.preventDefault();
            }
        });
    }

    /**
     * Handle touch start events
     */
    function handleTouchStart(event) {
        const touch = event.touches[0];
        state.touchStartX = touch.clientX;
        state.touchStartY = touch.clientY;
        state.touchStartTime = Date.now();

        // Store pull refresh start position
        if (window.scrollY === 0) {
            state.pullRefreshStartY = touch.clientY;
        }
    }

    /**
     * Handle touch move events
     */
    function handleTouchMove(event) {
        if (!event.touches[0]) return;

        const touch = event.touches[0];
        const deltaX = touch.clientX - state.touchStartX;
        const deltaY = touch.clientY - state.touchStartY;

        // Handle pull to refresh
        if (window.scrollY === 0 && deltaY > 0 && Math.abs(deltaX) < 50) {
            handlePullRefresh(deltaY);
        }

        // Prevent horizontal scrolling on album detail pages
        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 20) {
            const albumDetail = event.target.closest('.album-detail');
            if (albumDetail) {
                event.preventDefault();
            }
        }
    }

    /**
     * Handle touch end events
     */
    function handleTouchEnd(event) {
        const touch = event.changedTouches[0];
        const deltaX = touch.clientX - state.touchStartX;
        const deltaY = touch.clientY - state.touchStartY;
        const deltaTime = Date.now() - state.touchStartTime;
        const velocity = Math.sqrt(deltaX * deltaX + deltaY * deltaY) / deltaTime;

        // Handle swipe gestures
        if (Math.abs(deltaX) > CONFIG.SWIPE_THRESHOLD && velocity > CONFIG.SWIPE_VELOCITY_THRESHOLD) {
            handleSwipe(deltaX > 0 ? 'right' : 'left', event);
        }

        // Reset pull refresh
        if (state.isPullRefreshing) {
            finishPullRefresh();
        }

        // Reset touch state
        state.touchStartX = 0;
        state.touchStartY = 0;
        state.touchStartTime = 0;
    }

    /**
     * Handle swipe gestures
     */
    function handleSwipe(direction, event) {
        const target = event.target.closest('.album-card, .pagination, .album-detail');
        
        if (target) {
            if (target.classList.contains('album-detail')) {
                // Navigate between albums
                if (direction === 'left') {
                    navigateToNextAlbum();
                } else if (direction === 'right') {
                    navigateToPrevAlbum();
                }
            } else if (target.closest('.pagination')) {
                // Navigate pages
                if (direction === 'left') {
                    navigateToNextPage();
                } else if (direction === 'right') {
                    navigateToPrevPage();
                }
            }
        }
    }

    /**
     * Setup search functionality
     */
    function setupSearchEvents() {
        elements.searchInput.addEventListener('input', debounce(handleSearch, CONFIG.SEARCH_DEBOUNCE));
        elements.searchInput.addEventListener('focus', handleSearchFocus);
        elements.searchInput.addEventListener('blur', handleSearchBlur);
    }

    /**
     * Handle search input
     */
    function handleSearch(event) {
        const query = event.target.value.trim();
        
        if (query.length === 0) {
            clearSearchResults();
            return;
        }

        if (query.length < 2) {
            return;
        }

        performSearch(query);
    }

    /**
     * Perform live search
     */
    function performSearch(query) {
        // Show loading state
        showSearchLoading();

        // Use fetch for live search
        fetch(`/search?q=${encodeURIComponent(query)}&ajax=1`)
            .then(response => response.json())
            .then(data => {
                hideSearchLoading();
                updateSearchResults(data.albums);
            })
            .catch(error => {
                console.error('Search error:', error);
                hideSearchLoading();
            });
    }

    /**
     * Setup random button with vinyl animation
     */
    function setupRandomButton() {
        elements.randomButton.addEventListener('click', handleRandomButtonClick);
    }

    /**
     * Handle random button click with vinyl spin animation
     */
    function handleRandomButtonClick(event) {
        event.preventDefault();
        
        // Add vinyl button class if not present
        if (!elements.randomButton.classList.contains('btn-vinyl')) {
            elements.randomButton.classList.add('btn-vinyl');
        }

        // Add spinning animation
        elements.randomButton.classList.add('spinning');
        
        // Remove animation after duration
        setTimeout(() => {
            elements.randomButton.classList.remove('spinning');
            // Navigate to random album
            window.location.href = elements.randomButton.href;
        }, CONFIG.VINYL_SPIN_DURATION);

        // Add haptic feedback if available
        if (navigator.vibrate) {
            navigator.vibrate(50);
        }
    }

    /**
     * Setup album grid events
     */
    function setupAlbumGridEvents() {
        // Use enhanced cache-aware setup
        setupAlbumGridWithCache();
    }

    /**
     * Handle album card clicks
     */
    function handleAlbumClick(event) {
        const albumCard = event.target.closest('.album-card');
        if (!albumCard) return;

        // Add touch feedback
        albumCard.style.transform = 'scale(0.98)';
        setTimeout(() => {
            albumCard.style.transform = '';
        }, 150);

        // Navigate to album detail
        const albumLink = albumCard.getAttribute('data-href') || albumCard.querySelector('a')?.href;
        if (albumLink) {
            setTimeout(() => {
                window.location.href = albumLink;
            }, 150);
        }
    }

    /**
     * Setup keyboard shortcuts
     */
    function setupKeyboardEvents() {
        document.addEventListener('keydown', function(event) {
            // Skip if typing in input
            if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
                return;
            }

            switch (event.key.toLowerCase()) {
                case 'r':
                    event.preventDefault();
                    if (elements.randomButton) {
                        elements.randomButton.click();
                    }
                    break;
                case '/':
                    event.preventDefault();
                    if (elements.searchInput) {
                        elements.searchInput.focus();
                    }
                    break;
                case 'escape':
                    if (elements.searchInput && elements.searchInput === document.activeElement) {
                        elements.searchInput.blur();
                        clearSearchResults();
                    }
                    break;
                case 'arrowleft':
                    if (!state.isTouch) {
                        navigateToPrevPage();
                    }
                    break;
                case 'arrowright':
                    if (!state.isTouch) {
                        navigateToNextPage();
                    }
                    break;
            }
        });
    }

    /**
     * Setup window events
     */
    function setupWindowEvents() {
        // Scroll optimization
        let ticking = false;
        window.addEventListener('scroll', function() {
            if (!ticking) {
                requestAnimationFrame(handleScroll);
                ticking = true;
            }
        }, { passive: true });

        // Resize handler
        window.addEventListener('resize', debounce(handleResize, 250));

        // Online/offline detection
        window.addEventListener('online', handleOnline);
        window.addEventListener('offline', handleOffline);

        // Page visibility
        document.addEventListener('visibilitychange', handleVisibilityChange);
    }

    /**
     * Handle scroll events
     */
    function handleScroll() {
        // Header shadow effect
        if (elements.header) {
            const scrolled = window.scrollY > 10;
            elements.header.style.boxShadow = scrolled ? '0 2px 10px rgba(0,0,0,0.1)' : '';
        }

        // Infinite scroll (if needed)
        if (isNearBottom() && !state.isLoading) {
            loadMoreContent();
        }

        ticking = false;
    }

    /**
     * Setup intersection observer for lazy loading
     */
    function setupIntersectionObserver() {
        if (!('IntersectionObserver' in window)) {
            // Fallback: load all images immediately
            loadAllImages();
            return;
        }

        state.intersectionObserver = new IntersectionObserver(
            handleIntersectionWithCache,
            {
                rootMargin: '50px',
                threshold: CONFIG.INTERSECTION_THRESHOLD
            }
        );
    }

    /**
     * Handle intersection observer entries
     */
    function handleIntersection(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                loadImage(img);
                state.intersectionObserver.unobserve(img);
            }
        });
    }

    /**
     * Load image with lazy loading
     */
    function loadImage(img) {
        if (!img.dataset.src) return;

        // Add loading skeleton
        const container = img.closest('.album-cover');
        if (container) {
            container.classList.add('loading');
        }

        // Create new image to preload
        const newImg = new Image();
        newImg.onload = function() {
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
            
            if (container) {
                container.classList.remove('loading');
            }

            // Fade in animation
            img.style.opacity = '0';
            img.style.transition = 'opacity 0.3s';
            setTimeout(() => {
                img.style.opacity = '1';
            }, 10);
        };

        newImg.onerror = function() {
            if (container) {
                container.classList.remove('loading');
                container.innerHTML = '<div class="album-cover-placeholder">♪</div>';
            }
        };

        newImg.src = img.dataset.src;
    }

    /**
     * Setup pull to refresh
     */
    function setupPullToRefresh() {
        if (!state.isTouch) return;

        // Create pull refresh indicator
        const indicator = document.createElement('div');
        indicator.className = 'pull-refresh-indicator';
        indicator.innerHTML = '↓';
        elements.pullRefreshIndicator = indicator;
        
        const main = document.querySelector('.main');
        if (main) {
            main.style.position = 'relative';
            main.appendChild(indicator);
        }
    }

    /**
     * Handle pull to refresh
     */
    function handlePullRefresh(deltaY) {
        if (deltaY < 30 || state.isPullRefreshing) return;

        state.isPullRefreshing = true;
        
        if (elements.pullRefreshIndicator) {
            elements.pullRefreshIndicator.classList.add('visible');
            
            if (deltaY > 80) {
                elements.pullRefreshIndicator.innerHTML = '↑';
                elements.pullRefreshIndicator.style.transform = 'translateX(-50%) rotate(180deg)';
            }
        }
    }

    /**
     * Finish pull to refresh
     */
    function finishPullRefresh() {
        if (!state.isPullRefreshing) return;

        if (elements.pullRefreshIndicator) {
            elements.pullRefreshIndicator.classList.add('loading');
            elements.pullRefreshIndicator.innerHTML = '';
            
            // Simulate refresh
            setTimeout(() => {
                window.location.reload();
            }, 500);
        }
    }

    /**
     * Initialize components
     */
    function initializeComponents() {
        // Initialize sort controls
        initializeSortControls();
        
        // Initialize grid view toggle
        initializeGridToggle();
        
        // Initialize theme toggle
        initializeThemeToggle();
    }

    /**
     * Initialize sort controls
     */
    function initializeSortControls() {
        const sortBy = document.getElementById('sortBy');
        const sortOrder = document.getElementById('sortOrder');

        if (sortBy) {
            sortBy.addEventListener('change', updateSort);
        }

        if (sortOrder) {
            sortOrder.addEventListener('change', updateSort);
        }
    }

    /**
     * Update sort parameters
     */
    function updateSort() {
        const sortBy = document.getElementById('sortBy')?.value;
        const sortOrder = document.getElementById('sortOrder')?.value;
        const urlParams = new URLSearchParams(window.location.search);
        
        if (sortBy) urlParams.set('sort', sortBy);
        if (sortOrder) urlParams.set('order', sortOrder);
        urlParams.delete('page'); // Reset to first page when sorting
        
        // Show loading state
        showPageLoading();
        
        window.location.search = urlParams.toString();
    }

    /**
     * Initialize grid view toggle
     */
    function initializeGridToggle() {
        // Could be used for different grid layouts
        const savedLayout = localStorage.getItem('vinyl-grid-layout') || 'default';
        applyGridLayout(savedLayout);
    }

    /**
     * Apply grid layout
     */
    function applyGridLayout(layout) {
        if (elements.albumGrid) {
            elements.albumGrid.className = `album-grid album-grid-${layout}`;
        }
    }

    /**
     * Initialize theme toggle
     */
    function initializeThemeToggle() {
        const savedTheme = localStorage.getItem('vinyl-theme') || 'dark';
        applyTheme(savedTheme);
    }

    /**
     * Apply theme
     */
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('vinyl-theme', theme);
    }

    /**
     * Navigation helpers
     */
    function navigateToNextPage() {
        const nextLink = document.querySelector('.pagination a[href*="page=' + (state.currentPage + 1) + '"]');
        if (nextLink) {
            nextLink.click();
        }
    }

    function navigateToPrevPage() {
        const prevLink = document.querySelector('.pagination a[href*="page=' + (state.currentPage - 1) + '"]');
        if (prevLink) {
            prevLink.click();
        }
    }

    function navigateToNextAlbum() {
        const nextLink = document.querySelector('.album-nav .next');
        if (nextLink) {
            nextLink.click();
        }
    }

    function navigateToPrevAlbum() {
        const prevLink = document.querySelector('.album-nav .prev');
        if (prevLink) {
            prevLink.click();
        }
    }

    /**
     * Search helpers
     */
    function handleSearchFocus(event) {
        event.target.parentElement.classList.add('focused');
    }

    function handleSearchBlur(event) {
        event.target.parentElement.classList.remove('focused');
    }

    function showSearchLoading() {
        const searchForm = elements.searchInput?.parentElement;
        if (searchForm) {
            searchForm.classList.add('loading');
        }
    }

    function hideSearchLoading() {
        const searchForm = elements.searchInput?.parentElement;
        if (searchForm) {
            searchForm.classList.remove('loading');
        }
    }

    function clearSearchResults() {
        // Implementation depends on search results display
    }

    function updateSearchResults(albums) {
        // Implementation depends on search results display
    }

    /**
     * Loading states
     */
    function showPageLoading() {
        const indicator = document.createElement('div');
        indicator.className = 'page-loading';
        indicator.innerHTML = '<div class="loading-spinner"></div>';
        elements.body.appendChild(indicator);
    }

    function hidePageLoading() {
        const indicator = document.querySelector('.page-loading');
        if (indicator) {
            indicator.remove();
        }
    }

    /**
     * Utility functions
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function throttle(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    function isNearBottom() {
        return (window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 1000);
    }

    function loadMoreContent() {
        // Implementation for infinite scroll
        state.isLoading = true;
        // Load more albums...
    }

    function loadAllImages() {
        const images = document.querySelectorAll('img[data-src]');
        images.forEach(loadImage);
    }

    function handleResize() {
        // Handle responsive changes
    }

    function handleOnline() {
        console.log('Connection restored');
        // Sync any pending changes
    }

    function handleOffline() {
        console.log('Connection lost');
        // Show offline notification
    }

    function handleVisibilityChange() {
        if (document.hidden) {
            // Page is hidden
        } else {
            // Page is visible
            // Check for updates
        }
    }

    /**
     * Image Cache Management
     */
    
    /**
     * Enhanced image loading with cache support
     */
    function loadImageWithCache(img) {
        const originalUrl = img.dataset.originalSrc || img.dataset.src;
        const sizeType = img.dataset.sizeType || 'detail';
        
        if (!originalUrl) {
            console.warn('No original URL found for image:', img);
            return;
        }
        
        // Check if cached URL is already set
        if (img.src && img.src !== img.dataset.placeholder) {
            return;
        }
        
        // Show placeholder while loading
        const placeholderUrl = getPlaceholderUrl(sizeType);
        if (placeholderUrl && !img.src) {
            img.src = placeholderUrl;
        }
        
        // Check memory cache first
        const cacheKey = `${originalUrl}:${sizeType}`;
        const cachedUrl = state.imageCache.get(cacheKey);
        
        if (cachedUrl) {
            loadCachedImage(img, cachedUrl);
            return;
        }
        
        // Request cached image from server
        requestCachedImage(originalUrl, sizeType)
            .then(cachedUrl => {
                if (cachedUrl) {
                    state.imageCache.set(cacheKey, cachedUrl);
                    loadCachedImage(img, cachedUrl);
                } else {
                    handleImageLoadError(img);
                }
            })
            .catch(error => {
                console.error('Failed to load cached image:', error);
                handleImageLoadError(img);
            });
    }
    
    /**
     * Request cached image from server
     */
    async function requestCachedImage(originalUrl, sizeType) {
        try {
            // For now, we'll construct the expected cache URL
            // In a full implementation, you might query the server first
            const cacheUrl = await getCachedImageUrl(originalUrl, sizeType);
            
            // Test if the cached image exists
            const response = await fetch(cacheUrl, { method: 'HEAD' });
            if (response.ok) {
                return cacheUrl;
            }
            
            // If not cached, trigger caching on server
            await triggerImageCaching(originalUrl, sizeType);
            
            // Retry after a delay
            await new Promise(resolve => setTimeout(resolve, CONFIG.CACHE_RETRY_DELAY));
            
            const retryResponse = await fetch(cacheUrl, { method: 'HEAD' });
            if (retryResponse.ok) {
                return cacheUrl;
            }
            
            return null;
            
        } catch (error) {
            console.error('Error requesting cached image:', error);
            return null;
        }
    }
    
    /**
     * Get cached image URL (client-side URL construction)
     */
    async function getCachedImageUrl(originalUrl, sizeType) {
        // Create a simple hash of the URL for the filename
        const hash = await simpleHash(originalUrl);
        return `/cache/${sizeType}/${hash}.webp`;
    }
    
    /**
     * Simple hash function for client-side use
     */
    async function simpleHash(str) {
        const encoder = new TextEncoder();
        const data = encoder.encode(str);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    /**
     * Trigger image caching on server
     */
    async function triggerImageCaching(originalUrl, sizeType) {
        try {
            // This would make a request to the server to cache the image
            // For now, we'll skip this and assume the template helpers handle it
            return true;
        } catch (error) {
            console.error('Failed to trigger image caching:', error);
            return false;
        }
    }
    
    /**
     * Load cached image with fade-in effect
     */
    function loadCachedImage(img, cachedUrl) {
        const newImg = new Image();
        
        newImg.onload = () => {
            // Fade out placeholder
            img.style.opacity = '0.5';
            
            setTimeout(() => {
                img.src = cachedUrl;
                img.style.opacity = '1';
                img.classList.add('loaded');
                
                // Remove data attributes to prevent reloading
                img.removeAttribute('data-src');
                img.removeAttribute('data-original-src');
            }, 100);
        };
        
        newImg.onerror = () => {
            handleImageLoadError(img);
        };
        
        newImg.src = cachedUrl;
    }
    
    /**
     * Handle image load errors
     */
    function handleImageLoadError(img) {
        const sizeType = img.dataset.sizeType || 'detail';
        const placeholderUrl = getPlaceholderUrl(sizeType);
        
        if (placeholderUrl && img.src !== placeholderUrl) {
            img.src = placeholderUrl;
        }
        
        img.classList.add('error');
        console.warn('Failed to load image:', img.dataset.originalSrc || img.dataset.src);
    }
    
    /**
     * Get placeholder URL for size type
     */
    function getPlaceholderUrl(sizeType) {
        return `/cache/placeholders/placeholder_${sizeType}.webp`;
    }
    
    /**
     * Preload images for current page
     */
    function preloadCurrentPageImages() {
        if (state.isPreloading) {
            return;
        }
        
        const images = document.querySelectorAll('.album-cover img[data-original-src]');
        const urls = Array.from(images).map(img => img.dataset.originalSrc).filter(Boolean);
        
        if (urls.length === 0) {
            return;
        }
        
        preloadImageUrls(urls.slice(0, CONFIG.PRELOAD_BATCH_SIZE));
    }
    
    /**
     * Preload multiple image URLs
     */
    async function preloadImageUrls(urls) {
        if (state.isPreloading || urls.length === 0) {
            return;
        }
        
        state.isPreloading = true;
        
        try {
            const response = await fetch('/api/cache/preload', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ urls: urls })
            });
            
            if (response.ok) {
                const result = await response.json();
                console.log(`Preloaded ${result.preloaded}/${result.total} images`);
                
                // Update memory cache with successful preloads
                urls.forEach(url => {
                    if (result.results[url]) {
                        Promise.all([
                            getCachedImageUrl(url, 'thumbnails'),
                            getCachedImageUrl(url, 'detail')
                        ]).then(([thumbUrl, detailUrl]) => {
                            state.imageCache.set(`${url}:thumbnails`, thumbUrl);
                            state.imageCache.set(`${url}:detail`, detailUrl);
                        });
                    }
                });
            }
        } catch (error) {
            console.error('Preload failed:', error);
        } finally {
            state.isPreloading = false;
        }
    }
    
    /**
     * Enhanced intersection observer for image cache
     */
    function handleIntersectionWithCache(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                
                // Use enhanced cache-aware loading
                loadImageWithCache(img);
                
                // Stop observing this image
                if (state.intersectionObserver) {
                    state.intersectionObserver.unobserve(img);
                }
            }
        });
    }
    
    /**
     * Setup enhanced album grid with cache support
     */
    function setupAlbumGridWithCache() {
        if (!elements.albumGrid) return;
        
        // Setup click events
        elements.albumGrid.addEventListener('click', handleAlbumClick);
        
        // Setup enhanced lazy loading with cache
        const albumCovers = elements.albumGrid.querySelectorAll('.album-cover img[data-src], .album-cover img[data-original-src]');
        albumCovers.forEach(img => {
            // Ensure we have the original URL stored
            if (img.dataset.src && !img.dataset.originalSrc) {
                img.dataset.originalSrc = img.dataset.src;
            }
            
            // Determine size type from classes or data attributes
            if (img.closest('.album-grid')) {
                img.dataset.sizeType = 'thumbnails';
            } else {
                img.dataset.sizeType = 'detail';
            }
            
            if (state.intersectionObserver) {
                state.intersectionObserver.observe(img);
            }
        });
        
        // Preload visible images
        setTimeout(() => {
            preloadCurrentPageImages();
        }, 500);
    }
    
    /**
     * Cache management utilities
     */
    async function getCacheStats() {
        try {
            const response = await fetch('/api/cache/stats');
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.error('Failed to get cache stats:', error);
        }
        return null;
    }
    
    async function clearImageCache() {
        try {
            const response = await fetch('/api/cache/clear', { method: 'POST' });
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    state.imageCache.clear();
                    console.log('Image cache cleared successfully');
                    return true;
                }
            }
        } catch (error) {
            console.error('Failed to clear cache:', error);
        }
        return false;
    }
    
    /**
     * Performance optimizations for Raspberry Pi
     */
    function optimizeForPi() {
        // Reduce animations on slower hardware
        const userAgent = navigator.userAgent.toLowerCase();
        if (userAgent.includes('arm') || window.innerWidth <= 800) {
            document.documentElement.style.setProperty('--transition-fast', '0.1s');
            document.documentElement.style.setProperty('--transition-base', '0.15s');
            document.documentElement.style.setProperty('--transition-slow', '0.2s');
        }

        // Optimize scroll performance
        document.addEventListener('scroll', throttle(handleScroll, CONFIG.SCROLL_DEBOUNCE), { passive: true });
    }

    /**
     * Error handling
     */
    window.addEventListener('error', function(event) {
        console.error('JavaScript error:', event.error);
        // Could send to error tracking service
    });

    window.addEventListener('unhandledrejection', function(event) {
        console.error('Unhandled promise rejection:', event.reason);
        event.preventDefault();
    });

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Apply Pi optimizations
    optimizeForPi();

    // Expose some functions globally for HTML onclick handlers
    window.VinylVault = {
        updateSort: updateSort,
        applyTheme: applyTheme,
        applyGridLayout: applyGridLayout,
        getCacheStats: getCacheStats,
        clearImageCache: clearImageCache,
        preloadCurrentPageImages: preloadCurrentPageImages
    };

})();