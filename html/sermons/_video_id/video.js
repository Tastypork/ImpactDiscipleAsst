// Function to load config data
async function loadConfig() {
    try {
        const response = await fetch('config.json');
        if (!response.ok) throw new Error('Could not load config file');
        const config = await response.json();
        injectData(config);
    } catch (error) {
        console.error("Error loading config:", error);
    }
}

// Function to inject data into the HTML
function injectData(config) {
    // Video URL
    document.getElementById("videoFrame").src = config.videoUrl;

    // Summary
    document.getElementById("summaryText").textContent = config.summaryText;

    // Tags
    const tagContainer = document.getElementById("tagContainer");
    tagContainer.innerHTML = ''; // Clear any existing tags
    config.tags.forEach(tag => {
        const tagElement = document.createElement("a");
        tagElement.href = "#";
        tagElement.className = "badge badge-primary mr-2";
        tagElement.textContent = tag;
        tagContainer.appendChild(tagElement);
    });

    // Main Points
    const mainPointsContainer = document.getElementById("mainPoints");
    mainPointsContainer.innerHTML = ''; // Clear any existing points
    config.mainPoints.forEach(point => {
        const li = document.createElement("li");
        li.textContent = point;
        mainPointsContainer.appendChild(li);
    });

    // Verses Mentioned
    const versesContainer = document.getElementById("versesMentioned");
    versesContainer.innerHTML = ''; // Clear any existing verses
    config.versesMentioned.forEach(verse => {
        const li = document.createElement("li");
        li.innerHTML = `<strong>${verse.verse}</strong> - "${verse.text}"`;
        versesContainer.appendChild(li);
    });

    // Daily Action Plan
    const actionPlanContainer = document.getElementById("dailyActionPlan");
    actionPlanContainer.innerHTML = ''; // Clear any existing plans
    Object.keys(config.dailyActionPlan).forEach(day => {
        const dayData = config.dailyActionPlan[day];
        const dayDiv = document.createElement("div");
        dayDiv.innerHTML = `
            <h5>${day}</h5>
            <p><strong>Scripture Reflection:</strong> ${dayData.scripture}</p>
            <p><strong>Focus Point:</strong> ${dayData.focus}</p>
            <p><strong>Action Plan:</strong> ${dayData.action}</p>
            <p><strong>Deep Prayer:</strong> ${dayData.prayer}</p>
        `;
        actionPlanContainer.appendChild(dayDiv);
    });

    // Initialize the slider after all content is injected
    initializeSlider();
}

// Initialize or reinitialize the slider
function initializeSlider() {
    // Remove existing slider if initialized, then reinitialize
    if ($('.daily-action-plan-slider').hasClass('slick-initialized')) {
        $('.daily-action-plan-slider').slick('unslick'); // Destroy the previous slider instance
    }
    $('.daily-action-plan-slider').slick({
        slidesToShow: 2,
        slidesToScroll: 1,
        autoplay: true,
        autoplaySpeed: 2000,
        dots: true,
        arrows: true
    });
}


// Load the config and inject data
loadConfig();
