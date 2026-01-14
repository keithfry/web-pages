/**
 * LayoutEngine.js
 * Generates random overlapping layouts for image cloud
 * 
 * Public API:
 * - generateLayout(imageCount, containerBounds)
 * - getOriginalState(imageId)
 * - reset()
 */

class LayoutEngine {
    constructor(config = {}) {
        this.config = {
            rotationRange: config.rotationRange || 15,
            sizeVarianceMin: config.sizeVarianceMin || 0.8,
            sizeVarianceMax: config.sizeVarianceMax || 1.2,
            baseImageSize: config.baseImageSize || 200,
            padding: config.padding || 50,
            minSpacing: config.minSpacing || 20
        };
        
        this.layouts = new Map();  // Store original states by image ID
    }
    
    /**
     * Generate random layout positions for images
     * @param {number} imageCount - Number of images to layout
     * @param {Object} containerBounds - Container dimensions {width, height}
     * @returns {Array} - Array of layout objects with position, rotation, scale
     */
    generateLayout(imageCount, containerBounds) {
        const layouts = [];
        const { width, height } = containerBounds;
        const { padding, baseImageSize, rotationRange, sizeVarianceMin, sizeVarianceMax } = this.config;
        
        // Calculate safe bounds (accounting for image size and padding)
        const maxX = width - baseImageSize - padding;
        const maxY = height - baseImageSize - padding;
        const minX = padding;
        const minY = padding;
        
        for (let i = 0; i < imageCount; i++) {
            // Random position within safe bounds
            const x = this.random(minX, maxX);
            const y = this.random(minY, maxY);
            
            // Random rotation within range
            const rotation = this.random(-rotationRange, rotationRange);
            
            // Random size variance
            const scale = this.random(sizeVarianceMin, sizeVarianceMax);
            
            const layout = {
                id: i,
                x,
                y,
                rotation,
                scale,
                baseSize: baseImageSize
            };
            
            layouts.push(layout);
            this.layouts.set(i, layout);  // Store for later retrieval
        }
        
        return layouts;
    }
    
    /**
     * Get the original layout state for an image
     * @param {number|string} imageId - The image ID
     * @returns {Object} - Original layout state
     */
    getOriginalState(imageId) {
        return this.layouts.get(Number(imageId));
    }
    
    /**
     * Reset all stored layouts
     */
    reset() {
        this.layouts.clear();
    }
    
    /**
     * Utility: Generate random number between min and max
     * @param {number} min - Minimum value
     * @param {number} max - Maximum value
     * @returns {number}
     */
    random(min, max) {
        return Math.random() * (max - min) + min;
    }
    
    /**
     * Update config dynamically (useful for responsive changes)
     * @param {Object} newConfig - Updated configuration
     */
    updateConfig(newConfig) {
        Object.assign(this.config, newConfig);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LayoutEngine;
}
