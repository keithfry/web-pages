/**
 * RadialPlacementGenerator.js
 * Generates concentric radial layouts for image cloud
 */

class RadialPlacementGenerator {
    constructor(config) {
        this.config = config;
    }

    /**
     * Generate radial layout positions for images
     * @param {number} imageCount - Number of images to layout
     * @param {Object} containerBounds - Container dimensions {width, height}
     * @param {Object} options - Optional overrides
     * @returns {Array} - Array of layout objects with position, rotation, scale
     */
    generate(imageCount, containerBounds, options = {}) {
        const layouts = [];
        const { width, height } = containerBounds;
        const { baseImageSize, rotationRange } = this.config;
        
        // Use override fixedHeight if provided, else config fixedHeight, else baseImageSize
        const fixedHeight = options.fixedHeight || this.config.fixedHeight;
        const imageSize = fixedHeight || baseImageSize;
        const cx = width / 2;
        const cy = height / 2;
        
        // Initial placement at center
        const startX = cx - imageSize / 2; // Approximate centering ignoring aspect ratio width variance
        const startY = cy - imageSize / 2;
        
        // Add center image
        if (imageCount > 0) {
            layouts.push({
                id: 0,
                x: cx - (this.estimateWidth(imageSize) / 2),
                y: startY,
                rotation: this.random(-5, 5), // Less rotation for center
                scale: 1.0,
                baseSize: imageSize
            });
        }
        
        let processedCount = 1;
        let currentRing = 1;
        
        while (processedCount < imageCount) {
            // Ring settings
            // Scale X more than Y to create horizontal oval shape
            const radiusY = currentRing * (imageSize * 1.0); // Reduce overlap by increasing spacing (0.8 -> 1.0)
            const radiusX = radiusY * 1.5; // Horizontal stretching factor
            
            const circumference = Math.PI * (3 * (radiusX + radiusY) - Math.sqrt((3 * radiusX + radiusY) * (radiusX + 3 * radiusY))); // Ramanujan's approximation
            
            const estimatedItemWidth = this.estimateWidth(imageSize);
            // Increase spacing between items to reduce horizontal overlap
            const itemsInRing = Math.floor(circumference / (estimatedItemWidth * 1.1)); 
            
            if (itemsInRing === 0) {
                currentRing++;
                continue;
            }
            
            const angleStep = (2 * Math.PI) / itemsInRing;
            
            for (let i = 0; i < itemsInRing && processedCount < imageCount; i++) {
                const angle = i * angleStep;
                
                // Calculate center position of image using elliptical formula
                const centerX = cx + Math.cos(angle) * radiusX;
                const centerY = cy + Math.sin(angle) * radiusY;
                
                // Top-left position
                const x = centerX - (estimatedItemWidth / 2);
                const y = centerY - (imageSize / 2);
                
                const rotation = this.random(-rotationRange, rotationRange);
                
                layouts.push({
                    id: processedCount,
                    x,
                    y,
                    rotation,
                    scale: 1.0,
                    baseSize: imageSize
                });
                
                processedCount++;
            }
            
            currentRing++;
        }
        
        return layouts;
    }
    
    estimateWidth(height) {
        // Assume landscape aspect ratio approx 4:3 or 16:9 on average?
        // Let's assume 1.4 ratio
        return height * 1.4;
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
}
