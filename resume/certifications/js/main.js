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
const loadingEl = document.getElementById('loading');
const errorEl = document.getElementById('error');

// State
let imagesLoaded = false;
let imageElements = [];

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
    
    console.log('Interactive Image Cloud initialized');
    
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
        
        console.log(`Loaded ${imageUrls.length} images from Google Drive`);
        
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
    
    // Generate layout for images
    const layouts = layoutEngine.generateLayout(imageUrls.length, containerBounds);
    
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
                img.style.opacity = '1';
            });
            
            processedCount++;
        }
        
        // Stop interval if all images are processed
        if (processedCount >= imageUrls.length && displayQueue.length === 0) {
            // Check if we're truly done (all fetched and processed)
            // Ideally we track fetched count too, but checking length gives a good approximation
            // if we assume this runs long enough. 
            // Better: just check if we have processed all URLs provided.
            if (processedCount === imageUrls.length) {
                clearInterval(queueInterval);
            }
        }
    }, CONFIG.animation.queueInterval);

    // Create image elements
    imageUrls.forEach((url, index) => {
        const img = document.createElement('img');
        img.src = url;
        img.classList.add('cloud-image');
        img.dataset.imageId = index;
        
        // Apply initial layout
        const layout = layouts[index];
        const baseSize = CONFIG.isMobile() ? CONFIG.layout.mobileImageSize : layout.baseSize;
        const imageHeight = CONFIG.layout.fixedHeight;
        
        // Allow natural aspect ratio, constrained by fixed height
        img.style.width = 'auto';
        img.style.height = `${imageHeight}px`;
        
        img.style.left = `${layout.x}px`;
        img.style.top = `${layout.y}px`;
        
        // Apply initial transform (rotation and scale)
        img.style.transform = `rotate(${layout.rotation}deg) scale(${layout.scale})`;
        
        // Add click handler with stopPropagation to avoid triggering background click
        img.addEventListener('click', (e) => {
            e.stopPropagation();
            handleImageClick(img, layout);
        });
        
        // Set initial opacity for fade-in effect
        img.style.opacity = '0';
        img.style.transition = 'opacity 0.5s ease-in-out';
        
        // Wait for image to load before appending to queue
        img.onload = () => {
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
        // Optionally regenerate layout on significant resize
        console.log('Window resized');
    }, 500);
});

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
