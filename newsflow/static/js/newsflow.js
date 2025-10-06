/**
 * NewsFlow - AI-Powered News Aggregation Platform
 * Main JavaScript functionality
 *
 * Features:
 * - Article click tracking
 * - Bookmark management (authenticated & anonymous users)
 * - Share functionality
 * - Summary modal for mobile-optimized reading
 * - Toast notifications
 * - Keyboard shortcuts
 * - Theme usage analytics
 */

class NewsFlow {
    constructor() {
        this.currentShareUrl = '';
        this.currentShareTitle = '';
        this.currentShareArticleId = '';

        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeFeatures();
        });
    }

    initializeFeatures() {
        this.initializeBookmarkStates();
        this.initializeLikeStates();
        this.initializeSummaryFeatures();
        this.addEventListeners();
        this.trackThemeUsage();
        this.addKeyboardShortcuts();
    }

    // Event Listeners
    addEventListeners() {
        // Bookmark buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('.bookmark-btn')) {
                e.preventDefault();
                this.handleBookmarkClick(e.target.closest('.bookmark-btn'));
            }
        });

        // Like buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('.like-btn')) {
                e.preventDefault();
                this.handleLikeClick(e.target.closest('.like-btn'));
            }
        });

        // Share buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('.share-btn')) {
                e.preventDefault();
                e.stopPropagation();
                this.handleShareClick(e.target.closest('.share-btn'));
            }
        });

        // Summary toggle buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('.summary-toggle')) {
                e.preventDefault();
                e.stopPropagation();
                this.handleSummaryToggle(e.target.closest('.summary-toggle'));
            }
        });

        // Summary modal buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('.summary-modal-btn')) {
                e.preventDefault();
                e.stopPropagation();
                this.openSummaryModal(e.target.closest('.summary-modal-btn'));
            }
        });

        // Modal close handlers
        document.addEventListener('click', (e) => {
            const shareModal = document.getElementById('share-modal');
            const summaryModal = document.getElementById('summaryModal');

            if (e.target === shareModal) {
                this.closeShareModal();
            }

            if (e.target === summaryModal) {
                this.closeSummaryModal();
            }

            // Summary modal close button
            if (e.target.closest('.summary-close-btn')) {
                this.closeSummaryModal();
            }

            // Summary modal action buttons
            if (e.target.closest('.summary-bookmark-btn')) {
                e.preventDefault();
                this.handleSummaryBookmark(e.target.closest('.summary-bookmark-btn'));
            }

            if (e.target.closest('.summary-share-btn')) {
                e.preventDefault();
                this.handleSummaryShare();
            }

            if (e.target.closest('.summary-copy-btn')) {
                e.preventDefault();
                this.copySummaryToClipboard();
            }
        });
    }

    // Article Click Tracking
    trackArticleClick(articleId) {
        if (!articleId) return;

        fetch('/api/track-click/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify({
                article_id: articleId,
                timestamp: new Date().toISOString(),
                user_agent: navigator.userAgent,
                referrer: document.referrer
            })
        }).catch(error => {
            console.log('Analytics tracking failed:', error);
            // Don't let analytics failures affect user experience
        });
    }

    // Bookmark Management
    handleBookmarkClick(button) {
        const articleId = button.dataset.articleId;
        const articleTitle = button.dataset.articleTitle;
        const articleUrl = button.dataset.articleUrl;

        this.bookmarkArticle(button, articleId, articleTitle, articleUrl);
    }

    // Like Management
    handleLikeClick(button) {
        const articleId = button.dataset.articleId;
        const articleTitle = button.dataset.articleTitle;
        const articleUrl = button.dataset.articleUrl;

        this.likeArticle(button, articleId, articleTitle, articleUrl);
    }

    async bookmarkArticle(button, articleId, articleTitle, articleUrl) {
        try {
            const isAuthenticated = document.body.dataset.userAuthenticated === 'true';

            if (isAuthenticated) {
                await this.handleAuthenticatedBookmark(button, articleId);
            } else {
                this.handleAnonymousBookmark(button, articleId, articleTitle, articleUrl);
            }
        } catch (error) {
            console.error('Error bookmarking article:', error);
            this.showToast('Failed to bookmark article', 'error');
        }
    }

    async handleAuthenticatedBookmark(button, articleId) {
        const response = await fetch('/api/bookmark/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify({ article_id: articleId }),
        });

        const data = await response.json();

        if (data.status === 'success') {
            this.updateBookmarkButtonState(button, data.is_bookmarked);
            this.showToast(
                data.is_bookmarked ? 'Article bookmarked!' : 'Bookmark removed',
                data.is_bookmarked ? 'success' : 'info'
            );
        } else if (data.message === 'Authentication required') {
            this.showToast('Please sign in to bookmark articles', 'warning');
            setTimeout(() => {
                window.location.href = '/accounts/login/';
            }, 2000);
        } else {
            throw new Error(data.message);
        }
    }

    handleAnonymousBookmark(button, articleId, articleTitle, articleUrl) {
        const bookmarks = this.getLocalBookmarks();
        const articleData = {
            id: articleId,
            title: articleTitle,
            url: articleUrl,
            timestamp: Date.now()
        };

        const isBookmarked = bookmarks.some(bookmark => bookmark.id === articleId);

        if (isBookmarked) {
            const updatedBookmarks = bookmarks.filter(bookmark => bookmark.id !== articleId);
            localStorage.setItem('newsflow-bookmarks', JSON.stringify(updatedBookmarks));
            this.updateBookmarkButtonState(button, false);
            this.showToast('Bookmark removed', 'info');
        } else {
            bookmarks.push(articleData);
            localStorage.setItem('newsflow-bookmarks', JSON.stringify(bookmarks));
            this.updateBookmarkButtonState(button, true);
            this.showToast('Article bookmarked!', 'success');
        }
    }

    getLocalBookmarks() {
        try {
            const bookmarks = localStorage.getItem('newsflow-bookmarks');
            return bookmarks ? JSON.parse(bookmarks) : [];
        } catch (error) {
            console.error('Error reading bookmarks from localStorage:', error);
            return [];
        }
    }

    updateBookmarkButtonState(button, isBookmarked) {
        const svg = button.querySelector('svg');
        if (isBookmarked) {
            svg.setAttribute('fill', 'currentColor');
            button.classList.add('text-yellow-500');
            button.classList.remove('text-gray-400');
            button.setAttribute('title', 'Remove bookmark');
        } else {
            svg.setAttribute('fill', 'none');
            button.classList.remove('text-yellow-500');
            button.classList.add('text-gray-400');
            button.setAttribute('title', 'Bookmark');
        }
    }

    initializeBookmarkStates() {
        const isAuthenticated = document.body.dataset.userAuthenticated === 'true';

        if (!isAuthenticated) {
            const bookmarks = this.getLocalBookmarks();
            const bookmarkedIds = bookmarks.map(b => b.id);

            document.querySelectorAll('.bookmark-btn').forEach(button => {
                const articleId = button.dataset.articleId;
                if (bookmarkedIds.includes(articleId)) {
                    this.updateBookmarkButtonState(button, true);
                }
            });
        }
    }

    // Like Management
    async likeArticle(button, articleId, articleTitle, articleUrl) {
        try {
            const isAuthenticated = document.body.dataset.userAuthenticated === 'true';

            if (isAuthenticated) {
                await this.handleAuthenticatedLike(button, articleId);
            } else {
                this.handleAnonymousLike(button, articleId, articleTitle, articleUrl);
            }
        } catch (error) {
            console.error('Error liking article:', error);
            this.showToast('Failed to like article', 'error');
        }
    }

    async handleAuthenticatedLike(button, articleId) {
        const response = await fetch('/api/like/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify({ article_id: articleId }),
        });

        const data = await response.json();

        if (data.status === 'success') {
            this.updateLikeButtonState(button, data.is_liked);
            this.showToast(
                data.is_liked ? 'Article liked!' : 'Like removed',
                data.is_liked ? 'success' : 'info'
            );
        } else if (data.message === 'Authentication required') {
            this.showToast('Please sign in to like articles', 'warning');
            setTimeout(() => {
                window.location.href = '/accounts/login/';
            }, 2000);
        } else {
            throw new Error(data.message);
        }
    }

    handleAnonymousLike(button, articleId, articleTitle, articleUrl) {
        const likes = this.getLocalLikes();
        const articleData = {
            id: articleId,
            title: articleTitle,
            url: articleUrl,
            timestamp: Date.now()
        };

        const isLiked = likes.some(like => like.id === articleId);

        if (isLiked) {
            const updatedLikes = likes.filter(like => like.id !== articleId);
            localStorage.setItem('newsflow-likes', JSON.stringify(updatedLikes));
            this.updateLikeButtonState(button, false);
            this.showToast('Like removed', 'info');
        } else {
            likes.push(articleData);
            localStorage.setItem('newsflow-likes', JSON.stringify(likes));
            this.updateLikeButtonState(button, true);
            this.showToast('Article liked!', 'success');
        }
    }

    getLocalLikes() {
        try {
            const likes = localStorage.getItem('newsflow-likes');
            return likes ? JSON.parse(likes) : [];
        } catch (error) {
            console.error('Error reading likes from localStorage:', error);
            return [];
        }
    }

    updateLikeButtonState(button, isLiked) {
        const svg = button.querySelector('svg');
        if (isLiked) {
            svg.setAttribute('fill', 'currentColor');
            button.classList.add('text-red-500');
            button.classList.remove('text-gray-400');
            button.setAttribute('title', 'Unlike');
        } else {
            svg.setAttribute('fill', 'none');
            button.classList.remove('text-red-500');
            button.classList.add('text-gray-400');
            button.setAttribute('title', 'Like');
        }
    }

    initializeLikeStates() {
        const isAuthenticated = document.body.dataset.userAuthenticated === 'true';

        if (!isAuthenticated) {
            const likes = this.getLocalLikes();
            const likedIds = likes.map(l => l.id);

            document.querySelectorAll('.like-btn').forEach(button => {
                const articleId = button.dataset.articleId;
                if (likedIds.includes(articleId)) {
                    this.updateLikeButtonState(button, true);
                }
            });
        }
    }

    // Share Functionality
    handleShareClick(button) {
        const url = button.dataset.url;
        const title = button.dataset.title;
        const articleId = button.dataset.articleId;
        this.shareArticle(url, title, articleId);
    }

    shareArticle(url, title, articleId) {
        this.currentShareUrl = url;
        this.currentShareTitle = title;
        this.currentShareArticleId = articleId;

        const titleElement = document.getElementById('share-article-title');
        const modalElement = document.getElementById('share-modal');

        if (titleElement) {
            titleElement.textContent = title;
        }

        if (modalElement) {
            modalElement.classList.remove('hidden');
            document.body.classList.add('overflow-hidden');
        }
    }

    closeShareModal() {
        const modal = document.getElementById('share-modal');
        if (modal) {
            modal.classList.add('hidden');
            document.body.classList.remove('overflow-hidden');
        }
    }

    // Social Media Share Functions
    shareToWhatsApp() {
        const text = encodeURIComponent(`${this.currentShareTitle} ${this.currentShareUrl}`);
        window.open(`https://wa.me/?text=${text}`, '_blank');
        this.trackShare('whatsapp');
        this.closeShareModal();
    }

    shareToFacebook() {
        const url = encodeURIComponent(this.currentShareUrl);
        window.open(`https://www.facebook.com/sharer/sharer.php?u=${url}`, '_blank');
        this.trackShare('facebook');
        this.closeShareModal();
    }

    shareToTwitter() {
        const text = encodeURIComponent(this.currentShareTitle);
        const url = encodeURIComponent(this.currentShareUrl);
        window.open(`https://twitter.com/intent/tweet?text=${text}&url=${url}`, '_blank');
        this.trackShare('twitter');
        this.closeShareModal();
    }

    shareToLinkedIn() {
        const url = encodeURIComponent(this.currentShareUrl);
        const title = encodeURIComponent(this.currentShareTitle);
        window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${url}&title=${title}`, '_blank');
        this.trackShare('linkedin');
        this.closeShareModal();
    }

    shareToTelegram() {
        const text = encodeURIComponent(`${this.currentShareTitle} ${this.currentShareUrl}`);
        window.open(`https://t.me/share/url?url=${this.currentShareUrl}&text=${text}`, '_blank');
        this.trackShare('telegram');
        this.closeShareModal();
    }

    copyToClipboard() {
        navigator.clipboard.writeText(this.currentShareUrl).then(() => {
            this.showToast('Link copied to clipboard!', 'success');
        }).catch(() => {
            // Fallback for older browsers
            const tempInput = document.createElement('input');
            tempInput.value = this.currentShareUrl;
            document.body.appendChild(tempInput);
            tempInput.select();
            tempInput.setSelectionRange(0, 99999);

            try {
                document.execCommand('copy');
                this.showToast('Link copied to clipboard!', 'success');
            } catch (error) {
                this.showToast('Failed to copy link', 'error');
            }

            document.body.removeChild(tempInput);
        });

        this.trackShare('clipboard');
        this.closeShareModal();
    }

    // Share Tracking
    trackShare(platform) {
        if (!this.currentShareArticleId) return;

        fetch('/api/track-share/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify({
                article_id: this.currentShareArticleId,
                platform: platform
            })
        }).catch(error => {
            console.log('Share tracking failed:', error);
            // Don't let tracking failures affect user experience
        });
    }

    // Summary Management
    initializeSummaryFeatures() {
        // Add swipe support for mobile summary modal
        this.addMobileSummarySwipeSupport();
    }

    handleSummaryToggle(button) {
        const summaryContent = button.closest('.summary-content');
        if (!summaryContent) return;

        const shortText = summaryContent.querySelector('.summary-short');
        const fullText = summaryContent.querySelector('.summary-full');

        if (!shortText || !fullText) return;

        const isExpanded = !fullText.classList.contains('hidden');

        if (isExpanded) {
            // Collapse
            fullText.classList.add('hidden');
            shortText.classList.remove('hidden');
            button.textContent = 'Read more';
            button.setAttribute('aria-expanded', 'false');
        } else {
            // On mobile, open modal instead of expanding inline
            if (window.innerWidth < 768) {
                this.openSummaryModalFromToggle(button);
                return;
            }

            // Expand inline on desktop
            shortText.classList.add('hidden');
            fullText.classList.remove('hidden');
            button.textContent = 'Read less';
            button.setAttribute('aria-expanded', 'true');
        }
    }

    openSummaryModalFromToggle(button) {
        const newsCard = button.closest('.news-card');
        if (!newsCard) return;

        // Extract article data from the news card
        const title = newsCard.querySelector('h2, h3, h4')?.textContent || '';
        const summaryContent = newsCard.querySelector('.summary-full')?.textContent ||
                              newsCard.querySelector('.summary-short')?.textContent || '';
        const keywords = Array.from(newsCard.querySelectorAll('[class*="keyword"], [class*="#"]'))
                              .map(el => el.textContent.replace('#', ''))
                              .filter(Boolean);
        const articleLink = newsCard.querySelector('a[href]')?.href || '';
        const isBookmarked = newsCard.querySelector('.bookmark-btn[data-bookmarked="true"]') !== null;

        this.showSummaryModal(title, summaryContent, keywords, articleLink, isBookmarked);
    }

    openSummaryModal(button) {
        const articleId = button.dataset.articleId;
        const title = button.dataset.title || '';
        const summary = button.dataset.summary || '';
        const keywords = button.dataset.keywords ? button.dataset.keywords.split(',') : [];
        const url = button.dataset.url || '';
        const isBookmarked = button.dataset.bookmarked === 'true';

        this.showSummaryModal(title, summary, keywords, url, isBookmarked, articleId);
    }

    showSummaryModal(title, summary, keywords, url, isBookmarked, articleId) {
        const modal = document.getElementById('summaryModal');
        if (!modal) return;

        // Populate modal content
        const titleElement = modal.querySelector('.summary-title');
        const textElement = modal.querySelector('.summary-text p');
        const keywordsContainer = modal.querySelector('.summary-keywords .flex');
        const readFullButton = modal.querySelector('.summary-read-full');
        const bookmarkButton = modal.querySelector('.summary-bookmark-btn');

        if (titleElement) titleElement.textContent = title;
        if (textElement) textElement.textContent = summary;
        if (readFullButton) readFullButton.href = url;

        // Update bookmark button state
        if (bookmarkButton) {
            bookmarkButton.dataset.bookmarked = isBookmarked;
            bookmarkButton.dataset.articleId = articleId;
            this.updateBookmarkButtonState(bookmarkButton, isBookmarked);
        }

        // Populate keywords
        if (keywordsContainer) {
            keywordsContainer.innerHTML = '';
            keywords.slice(0, 5).forEach(keyword => {
                const keywordElement = document.createElement('span');
                keywordElement.className = 'text-xs bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-300 px-2 py-1 rounded';
                keywordElement.textContent = `#${keyword}`;
                keywordsContainer.appendChild(keywordElement);
            });
        }

        // Calculate and show reading time
        const readTimeElement = modal.querySelector('.summary-read-time');
        if (readTimeElement) {
            const readTime = Math.ceil(summary.split(' ').length / 200); // ~200 WPM
            readTimeElement.textContent = `~${readTime}min read`;
        }

        // Store current summary data
        this.currentSummaryData = { title, summary, url, articleId };

        // Show modal with animation
        modal.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');

        // Trigger animation
        requestAnimationFrame(() => {
            modal.classList.add('show');
        });

        // Track summary view
        this.trackSummaryView(articleId);
    }

    closeSummaryModal() {
        const modal = document.getElementById('summaryModal');
        if (!modal) return;

        modal.classList.remove('show');

        setTimeout(() => {
            modal.classList.add('hidden');
            document.body.classList.remove('overflow-hidden');
        }, 300);
    }

    handleSummaryBookmark(button) {
        const articleId = button.dataset.articleId;
        if (!articleId) return;

        // Use existing bookmark functionality
        this.handleBookmarkClick(button);
    }

    handleSummaryShare() {
        if (!this.currentSummaryData) return;

        const { title, url, articleId } = this.currentSummaryData;
        this.shareArticle(url, title, articleId);
    }

    copySummaryToClipboard() {
        if (!this.currentSummaryData) return;

        const { summary } = this.currentSummaryData;

        navigator.clipboard.writeText(summary).then(() => {
            this.showToast('Summary copied to clipboard!', 'success');
        }).catch(() => {
            // Fallback for older browsers
            const tempTextArea = document.createElement('textarea');
            tempTextArea.value = summary;
            document.body.appendChild(tempTextArea);
            tempTextArea.select();

            try {
                document.execCommand('copy');
                this.showToast('Summary copied to clipboard!', 'success');
            } catch (error) {
                this.showToast('Failed to copy summary', 'error');
            }

            document.body.removeChild(tempTextArea);
        });
    }

    addMobileSummarySwipeSupport() {
        let startY = 0;
        let currentY = 0;
        let modalContent = null;

        document.addEventListener('touchstart', (e) => {
            const modal = document.getElementById('summaryModal');
            if (!modal || modal.classList.contains('hidden')) return;

            modalContent = modal.querySelector('.summary-content');
            if (!modalContent) return;

            startY = e.touches[0].clientY;
        }, { passive: true });

        document.addEventListener('touchmove', (e) => {
            if (!modalContent) return;

            currentY = e.touches[0].clientY;
            const deltaY = currentY - startY;

            // Only allow downward swipes
            if (deltaY > 0) {
                const translateY = Math.min(deltaY * 0.5, 200);
                modalContent.style.transform = `translateY(${translateY}px)`;
            }
        }, { passive: true });

        document.addEventListener('touchend', () => {
            if (!modalContent) return;

            const deltaY = currentY - startY;

            if (deltaY > 150) {
                this.closeSummaryModal();
            } else {
                modalContent.style.transform = 'translateY(0)';
            }

            modalContent = null;
        }, { passive: true });
    }

    trackSummaryView(articleId) {
        if (!articleId) return;

        fetch('/api/track-summary-view/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify({
                article_id: articleId,
                timestamp: new Date().toISOString()
            })
        }).catch(error => {
            console.log('Summary view tracking failed:', error);
        });
    }

    // Toast Notifications
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed top-20 right-4 z-50 px-4 py-2 rounded-lg shadow-lg transition-all duration-300 transform translate-x-full ${
            type === 'success' ? 'bg-green-500 text-white' :
            type === 'error' ? 'bg-red-500 text-white' :
            type === 'warning' ? 'bg-yellow-500 text-black' :
            'bg-blue-500 text-white'
        }`;
        toast.textContent = message;

        document.body.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.classList.remove('translate-x-full');
        }, 100);

        // Remove after 3 seconds
        setTimeout(() => {
            toast.classList.add('translate-x-full');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }

    // Analytics
    trackThemeUsage() {
        const theme = localStorage.getItem('newsflow-theme') || 'system';
        const isDarkMode = document.documentElement.classList.contains('dark');

        // Track theme preference (anonymously)
        if (typeof gtag !== 'undefined') {
            gtag('event', 'theme_usage', {
                theme_preference: theme,
                is_dark_mode: isDarkMode
            });
        }
    }

    // Keyboard Shortcuts
    addKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K for search focus
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.querySelector('input[name="q"]');
                if (searchInput) {
                    searchInput.focus();
                    searchInput.select();
                }
            }

            // Escape key handlers
            if (e.key === 'Escape') {
                this.closeShareModal();
                this.closeSummaryModal();

                // Hide search suggestions
                const suggestions = document.getElementById('search-suggestions');
                if (suggestions) {
                    suggestions.classList.add('hidden');
                }
            }
        });
    }

    // Utility Functions
    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
               document.querySelector('meta[name=csrf-token]')?.getAttribute('content') ||
               document.cookie
                 .split('; ')
                 .find(row => row.startsWith('csrftoken='))
                 ?.split('=')[1] || '';
    }

    scrollToTop() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    }
}

// Global Functions (for compatibility with existing HTML)
function trackArticleClick(articleId) {
    window.newsflow.trackArticleClick(articleId);
}

function shareToWhatsApp() {
    window.newsflow.shareToWhatsApp();
}

function shareToFacebook() {
    window.newsflow.shareToFacebook();
}

function shareToTwitter() {
    window.newsflow.shareToTwitter();
}

function shareToLinkedIn() {
    window.newsflow.shareToLinkedIn();
}

function shareToTelegram() {
    window.newsflow.shareToTelegram();
}

function copyToClipboard() {
    window.newsflow.copyToClipboard();
}

function scrollToTop() {
    window.newsflow.scrollToTop();
}

// Initialize NewsFlow
window.newsflow = new NewsFlow();
