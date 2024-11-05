(function ($) {
    "use strict";
    
    // Sticky Navbar
    $(window).scroll(function () {
        if ($(this).scrollTop() > 150) {
            $('.nav-bar').addClass('nav-sticky');
        } else {
            $('.nav-bar').removeClass('nav-sticky');
        }
    });
    
    
    // Dropdown on mouse hover
    $(document).ready(function () {
        function toggleNavbarMethod() {
            if ($(window).width() > 768) {
                $('.navbar .dropdown').on('mouseover', function () {
                    $('.dropdown-toggle', this).trigger('click');
                }).on('mouseout', function () {
                    $('.dropdown-toggle', this).trigger('click').blur();
                });
            } else {
                $('.navbar .dropdown').off('mouseover').off('mouseout');
            }
        }
        toggleNavbarMethod();
        $(window).resize(toggleNavbarMethod);
    });
    
    
    // Back to top button
    $(window).scroll(function () {
        if ($(this).scrollTop() > 100) {
            $('.back-to-top').fadeIn('slow');
        } else {
            $('.back-to-top').fadeOut('slow');
        }
    });
    $('.back-to-top').click(function () {
        $('html, body').animate({scrollTop: 0}, 1500, 'easeInOutExpo');
        return false;
    });
    
    
    // Top News Slider
    $('.tn-slider').slick({
        autoplay: true,
        infinite: true,
        dots: false,
        slidesToShow: 1,
        slidesToScroll: 1
    });
    
    
    // Category News Slider
    $('.cn-slider').slick({
        autoplay: false,
        infinite: false,
        dots: false,
        slidesToShow: 4,
        slidesToScroll: 2,
        responsive: [
            {
                breakpoint: 1200,
                settings: {
                    slidesToShow: 2
                }
            },
            {
                breakpoint: 992,
                settings: {
                    slidesToShow: 1
                }
            },
            {
                breakpoint: 768,
                settings: {
                    slidesToShow: 2
                }
            },
            {
                breakpoint: 576,
                settings: {
                    slidesToShow: 1
                }
            }
        ]
    });
    
    
    // Related News Slider
    $('.sn-slider').slick({
        autoplay: false,
        infinite: true,
        dots: false,
        slidesToShow: 3,
        slidesToScroll: 1,
        responsive: [
            {
                breakpoint: 1200,
                settings: {
                    slidesToShow: 3
                }
            },
            {
                breakpoint: 992,
                settings: {
                    slidesToShow: 3
                }
            },
            {
                breakpoint: 768,
                settings: {
                    slidesToShow: 2
                }
            },
            {
                breakpoint: 576,
                settings: {
                    slidesToShow: 1
                }
            }
        ]
    });
    // Load Sermon Slides Function
    async function loadSermonSlides() {
        try {
            // Fetch the latest sermons data from the JSON file
            const response = await fetch('latest_sermons.json');
            const sermons = await response.json();

            // Select the containers where content will be inserted
            const leftContainer = document.querySelector(".tn-left .tn-slider");
            const rightContainer = document.querySelector(".tn-right .row");

            // Clear existing content in the containers
            leftContainer.innerHTML = '';
            rightContainer.innerHTML = '';

            // Loop over the first 4 sermons in the JSON data
            sermons.slice(0, 8).forEach((sermon, index) => {

                const col = document.createElement("div");
                col.className = `col-md-6`;

                const link = document.createElement("a");
                link.href = sermon.summary_link; // Set the href for the link

                const sermonDiv = document.createElement("div");
                sermonDiv.className = "tn-img";

                const img = document.createElement("img");
                img.src = sermon.thumbnail_url;

                // Add the title only to the left container
                const titleDiv = document.createElement("div");
                titleDiv.className = "tn-title";

                const titleLink = document.createElement("a");
                titleLink.href = sermon.summary_link;
                titleLink.textContent = sermon.title;

                titleDiv.appendChild(titleLink);
                sermonDiv.appendChild(img);
                sermonDiv.appendChild(titleDiv);
                link.appendChild(sermonDiv);
                col.appendChild(link);

                const rightCol = col.cloneNode(true);

                // Add to the left or right container based on the index
                leftContainer.appendChild(col);
                rightContainer.appendChild(rightCol);
            });
            // Destroy existing Slick instance if it exists
            $(leftContainer).slick('unslick');

            // Reinitialize the slider after adding content
            $(leftContainer).slick({
                autoplay: true,
                infinite: true,
                dots: false,
                slidesToShow: 1,
                slidesToScroll: 1
            });
        } catch (error) {
            console.error("Error loading sermon slides:", error);
        }
    }

    // Call loadSermonSlides on document ready
    $(document).ready(function () {
        loadSermonSlides();
    });

    async function loadCategoryNews() {
        try {
            // Fetch the JSON data
            const response = await fetch('latest_sermons.json');
            const sermons = await response.json();
    
            // Select the .cn-slider container in .cat-news
            const cnSliderContainer = document.querySelector(".cat-news .cn-slider");
    
            // Clear any existing content in the container
            cnSliderContainer.innerHTML = '';
    
            // Loop over the 9th to 20th items (index 8 to 19) in the JSON data
            sermons.slice(8, 18).forEach((sermon) => {
                const col = document.createElement("div");
                col.className = `col-md-6`;

                const link = document.createElement("a");
                link.href = sermon.summary_link; // Set the href for the link

                const sermonDiv = document.createElement("div");
                sermonDiv.className = "cn-img";

                const img = document.createElement("img");
                img.src = sermon.thumbnail_url;
    
                // Assemble the structure
                sermonDiv.appendChild(img);
                link.appendChild(sermonDiv);
                col.appendChild(link);
    
                // Append to the .cn-slider container
                cnSliderContainer.appendChild(col);
            });

            // Destroy existing Slick instance if it exists
            $(cnSliderContainer).slick('unslick');

            // Reinitialize the slider after adding content
            $(cnSliderContainer).slick({
                autoplay: false,
                infinite: false,
                dots: false,
                slidesToShow: 4,
                slidesToScroll: 2,
                responsive: [
                    {
                        breakpoint: 1200,
                        settings: {
                            slidesToShow: 2
                        }
                    },
                    {
                        breakpoint: 992,
                        settings: {
                            slidesToShow: 1
                        }
                    },
                    {
                        breakpoint: 768,
                        settings: {
                            slidesToShow: 2
                        }
                    },
                    {
                        breakpoint: 576,
                        settings: {
                            slidesToShow: 1
                        }
                    }
                ]
            });
            
        } catch (error) {
            console.error("Error loading category news slides:", error);
        }
    }
    
    // Call the function on document ready
    $(document).ready(function () {
        loadCategoryNews();
    });

    async function loadMainNews() {
        try {
            // Fetch the JSON data
            const response = await fetch('latest_sermons.json');
            const sermons = await response.json();
    
            // Select the main-news container where content will be inserted
            const mainNewsContainer = document.querySelector(".main-news .container");
    
            // Clear any existing content in the container
            mainNewsContainer.innerHTML = '';
    
            // Group sermons by year and month
            const groupedSermons = {};
            sermons.forEach((sermon) => {
                const date = new Date(sermon.date);
                const year = date.getFullYear();
                const month = date.toLocaleString('default', { month: 'long' });
    
                if (!groupedSermons[year]) groupedSermons[year] = {};
                if (!groupedSermons[year][month]) groupedSermons[year][month] = [];
                groupedSermons[year][month].push(sermon);
            });
    
            // Sort years in descending order
            const sortedYears = Object.keys(groupedSermons).sort((a, b) => b - a);
    
            // Loop through sorted years and dynamically create headers and sections
            sortedYears.forEach((year) => {
                // Create a header for the year
                const yearHeader = document.createElement("h2");
                yearHeader.textContent = year;
                mainNewsContainer.appendChild(yearHeader);
    
                // Sort months in descending order (newest first)
                const sortedMonths = Object.keys(groupedSermons[year]).sort((a, b) => {
                    const dateA = new Date(`${year} ${a}`);
                    const dateB = new Date(`${year} ${b}`);
                    return dateB - dateA;
                });
    
                // Loop through each month in the current year
                sortedMonths.forEach((month) => {
                    // Create a header for the month
                    const monthHeader = document.createElement("h3");
                    monthHeader.textContent = month;
                    mainNewsContainer.appendChild(monthHeader);
    
                    // Create a row container for the videos in this month
                    const rowContainer = document.createElement("div");
                    rowContainer.className = "row";
    
                    // Loop through each sermon in the current month
                    groupedSermons[year][month].forEach((sermon) => {
                        const col = document.createElement("div");
                        col.className = "col-md-3";
    
                        // Create mn-img div for image and title
                        const mnImgDiv = document.createElement("div");
                        mnImgDiv.className = "mn-img";
    
                        const img = document.createElement("img");
                        img.src = sermon.thumbnail_url;
                        img.alt = `Thumbnail for ${sermon.title}`;
    
                        const titleDiv = document.createElement("div");
                        titleDiv.className = "mn-title";
    
                        const titleLink = document.createElement("a");
                        titleLink.href = sermon.summary_link;
                        titleLink.textContent = sermon.title;
    
                        // Append image and title to mn-img div
                        titleDiv.appendChild(titleLink);
                        mnImgDiv.appendChild(img);
                        mnImgDiv.appendChild(titleDiv);
    
                        // Create mn-tags div for tags
                        const tagsDiv = document.createElement("div");
                        tagsDiv.className = "mn-tags mt-2";
    
                        // Loop through tags in the JSON and create badge elements
                        sermon.tags.forEach((tag) => {
                            const tagLink = document.createElement("a");
                            tagLink.href = "#"; // Adjust as needed for tag link
                            tagLink.className = "badge badge-primary mr-2";
                            tagLink.textContent = tag;
                            tagsDiv.appendChild(tagLink);
                        });
    
                        // Append mn-img and mn-tags to the col div
                        col.appendChild(mnImgDiv);
                        col.appendChild(tagsDiv);
    
                        // Append the col div to the row container for this month
                        rowContainer.appendChild(col);
                    });
    
                    // Append the row container under the month header
                    mainNewsContainer.appendChild(rowContainer);
                });
            });
        } catch (error) {
            console.error("Error loading main news items:", error);
        }
    }
    
    // Call the function on document ready
    $(document).ready(function () {
        loadMainNews();
    });
    

})(jQuery);

