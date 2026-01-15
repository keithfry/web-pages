/**
 * main.js
 * Main application entry point
 * Coordinates all modules to create the interactive image cloud
 */

// Initialize modules
const animationEngine = new AnimationEngine(CONFIG.animation);
const layoutEngine = new LayoutEngine(CONFIG.layout);
const zoomEngine = new ZoomEngine(CONFIG.zoom, animationEngine);
const driveLoader = new GoogleDriveLoader(CONFIG.googleDrive);

// DOM elements
const imageCloud = document.getElementById('imageCloud');

// Polyfill debugLog if config.js failed to load or is cached without it
if (typeof window.debugLog !== 'function') {
    window.debugLog = function(...args) {
        // Fallback: log to console if debugging might be intended, or suppress
        // Checking for CONFIG existence just in case
        if (typeof CONFIG !== 'undefined' && CONFIG.debugLogging) {
            console.log(...args);
        }
    };
}
const loadingEl = document.getElementById('loading');
const errorEl = document.getElementById('error');

// State
let imagesLoaded = false;
let imageElements = [];
let currentImageHeight = 225; // Default fallback

// Configuration
const DEFAULT_DRIVE_FOLDER = 'https://drive.google.com/drive/folders/19JY4GPJkTIVa5DwrqNftYOuJfGUWRU5t?usp=sharing';

/**
 * Initialize the application
 */
function init() {
    // Add global event listeners for interaction
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            zoomEngine.unfocusImage();
        }
    });

    document.addEventListener('click', (e) => {
        // If user clicks background (not an image), reset zoom
        if (!e.target.closest('.cloud-image')) {
            zoomEngine.unfocusImage();
        }
    });
    
    debugLog('Interactive Image Cloud initialized');
    
    // Auto-load images
    handleLoadImages(DEFAULT_DRIVE_FOLDER);
}

/**
 * Handle loading images from Google Drive folder
 */
async function handleLoadImages(folderUrl) {
    if (!folderUrl) {
        showError('No folder URL provided');
        return;
    }
    
    try {
        showLoading(true);
        hideError();
        
        // Clear existing images
        clearImageCloud();
        
        // Load images from Google Drive
        const imageUrls = await driveLoader.loadImagesFromFolder(folderUrl);
        
        if (imageUrls.length === 0) {
            showError('No images found in the folder. Please make sure the folder contains image files.');
            showLoading(false);
            return;
        }
        
        debugLog(`Loaded ${imageUrls.length} images from Google Drive`);
        
        // Create and display images
        await createImageCloud(imageUrls);
        
        showLoading(false);
        imagesLoaded = true;
        
    } catch (error) {
        console.error('Error loading images:', error);
        showError(error.message || 'Failed to load images. Please check the folder URL and permissions.');
        showLoading(false);
    }
}

/**
 * Create the image cloud with random layout
 */
async function createImageCloud(imageUrls) {
    // Get container bounds
    const containerBounds = {
        width: imageCloud.offsetWidth,
        height: imageCloud.offsetHeight || window.innerHeight * 0.7
    };
    
    // Determine layout options
    const imageHeight = getImageHeight();
    currentImageHeight = imageHeight;
    
    // Generate layout for images with dynamic height
    const layouts = layoutEngine.generateLayout(imageUrls.length, containerBounds, { fixedHeight: imageHeight });
    
    // Queue for loaded images
    const displayQueue = [];
    let processedCount = 0;
    
    // Process queue interval
    const queueInterval = setInterval(() => {
        if (displayQueue.length > 0) {
            const img = displayQueue.shift();
            
            imageCloud.appendChild(img);
            imageElements.push(img);
            
            // Add entrance animation
            requestAnimationFrame(() => {
                // Force reflow to ensure the initial transform is applied before transition starts
                void img.offsetWidth;
                
                img.style.opacity = '1';
                // Animate to final transform (remove translation offset)
                img.style.transform = img.dataset.finalTransform;
            });
            
            processedCount++;
        }
        
        // Stop interval if all images are processed
        if (processedCount >= imageUrls.length && displayQueue.length === 0) {
            if (processedCount === imageUrls.length) {
                clearInterval(queueInterval);
            }
        }
    }, CONFIG.animation.queueInterval);

    // Create image elements
    imageUrls.forEach((url, index) => {
        const img = document.createElement('img');
        img.src = url;
        // IMPORTANT: Prevent "403 Forbidden" by not sending "localhost" referrer
        img.referrerPolicy = 'no-referrer';
        img.classList.add('cloud-image');
        img.dataset.imageId = index;
        
        // Apply initial layout
        const layout = layouts[index];
        const baseSize = CONFIG.isMobile() ? CONFIG.layout.mobileImageSize : layout.baseSize;
        // Use the calculated height
        // const imageHeight = CONFIG.layout.fixedHeight; // REMOVED
        
        // Allow natural aspect ratio, constrained by fixed height
        img.style.width = 'auto';
        img.style.height = `${imageHeight}px`;
        
        img.style.left = `${layout.x}px`;
        img.style.top = `${layout.y}px`;
        
        // Apply initial transform (rotation and scale)
        img.style.transform = `rotate(${layout.rotation}deg) scale(${layout.scale})`;

        // Debug: Apply border if specified
        if (layout.borderColor) {
            img.style.border = `5px solid ${layout.borderColor}`;
            img.style.boxSizing = 'border-box'; // Ensure border doesn't add to width
        }
        
        // Apply Z-Index for radial layering
        if (layout.zIndex) {
            img.style.zIndex = layout.zIndex;
        }
        
        // Add click handler with stopPropagation to avoid triggering background click
        img.addEventListener('click', (e) => {
            e.stopPropagation();
            handleImageClick(img, layout);
        });
        
        // Set initial opacity for fade-in effect
        img.style.opacity = '0';
        // Add transform to transition for floating effect, match duration with opacity or make it longer/smoother
        img.style.transition = 'opacity 0.6s ease-out, transform 0.8s cubic-bezier(0.25, 1, 0.5, 1)';
        
        // Wait for image to load before appending to queue
        img.onload = () => {
            // Task 4: Ensure placement keeps (x + width) and (y + height) with screen bounds
            // Moved logic to RadialPlacementGenerator.js
            
            const aspectRatio = img.naturalWidth / img.naturalHeight;
            const renderedWidth = imageHeight * aspectRatio;
            const containerWidth = containerBounds.width;
            const containerHeight = containerBounds.height;
            
            // Adjust X if too far right
            // Removed: Logic moved to generator
            
            // Adjust X if too far left
            // Removed: Logic moved to generator

            // Adjust Y if too far down (less likely with fixed height logic but good safety)
            // Removed: Logic moved to generator

            // Adjust Y if too far up
            // Removed: Logic moved to generator

            // Process Task 3: Animate images floating into position from a nearby border
            // Determine closest border
            const centerX = layout.x + renderedWidth / 2;
            const centerY = layout.y + imageHeight / 2;
            
            let startTx = 0;
            let startTy = 0;
            
            // Distances to borders
            const distLeft = centerX;
            const distRight = containerWidth - centerX;
            const distTop = centerY;
            const distBottom = containerHeight - centerY;
            
            const minDist = Math.min(distLeft, distRight, distTop, distBottom);
            
            // Set start translation to move it just off-screen
            // We add extra buffer to ensure it's fully off-screen
            const buffer = 100; 
            
            if (minDist === distLeft) {
                startTx = -(layout.x + renderedWidth + buffer);
            } else if (minDist === distRight) {
                startTx = (containerWidth - layout.x) + buffer;
            } else if (minDist === distTop) {
                startTy = -(layout.y + imageHeight + buffer);
            } else {
                startTy = (containerHeight - layout.y) + buffer;
            }
            
            // Store final transform for animation
            const finalTransform = `rotate(${layout.rotation}deg) scale(${layout.scale})`;
            const startTransform = `translate(${startTx}px, ${startTy}px) ${finalTransform}`;
            
            // Apply start state
            img.style.transform = startTransform;
            
            // Store final state on element for easy access in queue
            img.dataset.finalTransform = finalTransform;

            displayQueue.push(img);
        };
        
        img.onerror = () => {
            console.error(`Failed to load image: ${url}`);
            // Increment processed count so the interval eventually clears
             processedCount++; 
        };
    });
}

/**
 * Handle image click (focus/unfocus)
 */
async function handleImageClick(imageElement, originalLayout) {
    const isFocused = zoomEngine.isFocused(imageElement);
    
    // Get current container bounds
    const containerBounds = {
        width: imageCloud.offsetWidth,
        height: imageCloud.offsetHeight
    };
    
    if (isFocused) {
        // Unfocus the image
        await zoomEngine.unfocusImage();
    } else {
        // Focus the image
        await zoomEngine.focusImage(imageElement, containerBounds, originalLayout);
    }
}

/**
 * Clear the image cloud
 */
function clearImageCloud() {
    imageCloud.innerHTML = '';
    imageElements = [];
    layoutEngine.reset();
    zoomEngine.reset();
    imagesLoaded = false;
}

/**
 * Show/hide loading state
 */
function showLoading(show) {
    if (!CONFIG.ui.showLoadingSpinner) return;
    
    if (show) {
        loadingEl.classList.remove('hidden');
    } else {
        loadingEl.classList.add('hidden');
    }
}

/**
 * Show error message
 */
function showError(message) {
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
}

/**
 * Hide error message
 */
function hideError() {
    errorEl.classList.add('hidden');
}

/**
 * Handle window resize (regenerate layout if needed)
 */
let resizeTimeout;
window.addEventListener('resize', () => {
    if (!imagesLoaded) return;
    
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        // optionally regenerate layout on significant resize
        const newHeight = getImageHeight();
        
        if (newHeight !== currentImageHeight) {
            debugLog(`Window resized to new breakpoint (height: ${newHeight}px). Reloading images...`);
            handleLoadImages(DEFAULT_DRIVE_FOLDER);
        } else {
             // Just logging for minor resizes
             debugLog('Window resized (no breakpoint change)');
        }
    }, 500);
});

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

/**
 * Get image height based on window width
 */
function getImageHeight() {
    const width = window.innerWidth;
    const heights = CONFIG.layout.responsiveHeights || [];
    
    // Sort descending by minWidth to find first match
    for (const bh of heights) {
        if (width >= bh.minWidth) {
            return bh.height;
        }
    }
    return 120; // Fallback
}
