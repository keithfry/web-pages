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
const folderInput = document.getElementById('folderUrl');
const loadBtn = document.getElementById('loadBtn');
const imageCloud = document.getElementById('imageCloud');
const loadingEl = document.getElementById('loading');
const errorEl = document.getElementById('error');

// State
let imagesLoaded = false;
let imageElements = [];

/**
 * Initialize the application
 */
function init() {
    // Set up event listeners
    loadBtn.addEventListener('click', handleLoadImages);
    folderInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleLoadImages();
        }
    });
    
    // Pre-fill with test URL if available
    const testUrl = 'https://drive.google.com/drive/folders/19JY4GPJkTIVa5DwrqNftYOuJfGUWRU5t?usp=sharing';
    folderInput.value = testUrl;

    // Add global event listeners for interaction
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            zoomEngine.unfocusImage();
        }
    });

    document.addEventListener('click', (e) => {
        // If user clicks background (not an image or control), reset zoom
        if (!e.target.closest('.cloud-image') && 
            !e.target.closest('.input-wrapper') && 
            !e.target.closest('.instructions')) {
            zoomEngine.unfocusImage();
        }
    });
    
    console.log('Interactive Image Cloud initialized');
}

/**
 * Handle loading images from Google Drive folder
 */
async function handleLoadImages() {
    const folderUrl = folderInput.value.trim();
    
    if (!folderUrl) {
        showError('Please enter a Google Drive folder URL');
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
    
    // Create image elements
    const imagePromises = imageUrls.map((url, index) => {
        return new Promise((resolve, reject) => {
            const img = document.createElement('img');
            img.src = url;
            img.classList.add('cloud-image');
            img.dataset.imageId = index;
            
            // Apply initial layout
            const layout = layouts[index];
            const baseSize = CONFIG.isMobile() ? CONFIG.layout.mobileImageSize : layout.baseSize;
            
            // Allow natural aspect ratio, constrained by baseSize
            img.style.width = 'auto';
            img.style.height = 'auto';
            img.style.maxWidth = `${baseSize}px`;
            img.style.maxHeight = `${baseSize}px`;
            
            img.style.left = `${layout.x}px`;
            img.style.top = `${layout.y}px`;
            
            // Apply initial transform (rotation and scale)
            img.style.transform = `rotate(${layout.rotation}deg) scale(${layout.scale})`;
            
            // Add click handler with stopPropagation to avoid triggering background click
            img.addEventListener('click', (e) => {
                e.stopPropagation();
                handleImageClick(img, layout);
            });
            
            // Wait for image to load
            img.onload = () => {
                imageCloud.appendChild(img);
                imageElements.push(img);
                
                // Add entrance animation
                setTimeout(() => {
                    img.style.opacity = '1';
                }, index * 50); // Stagger entrance
                
                resolve();
            };
            
            img.onerror = () => {
                console.error(`Failed to load image: ${url}`);
                resolve(); // Continue even if one image fails
            };
            
            // Set initial opacity for fade-in effect
            img.style.opacity = '0';
            img.style.transition = 'opacity 0.5s ease-in-out';
        });
    });
    
    // Wait for all images to load
    await Promise.all(imagePromises);
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
    if (show) {
        loadingEl.classList.remove('hidden');
        loadBtn.disabled = true;
    } else {
        loadingEl.classList.add('hidden');
        loadBtn.disabled = false;
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
