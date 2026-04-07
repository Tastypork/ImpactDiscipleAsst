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
            const sortedSermons = [...sermons].sort((a, b) => {
                const aDate = new Date(a.date);
                const bDate = new Date(b.date);
                const aTime = Number.isNaN(aDate.getTime()) ? 0 : aDate.getTime();
                const bTime = Number.isNaN(bDate.getTime()) ? 0 : bDate.getTime();
                return bTime - aTime;
            });

            // Select the containers where content will be inserted
            const leftContainer = document.querySelector(".tn-left .tn-slider");
            const rightContainer = document.querySelector(".tn-right .row");

            // Clear existing content in the containers
            leftContainer.innerHTML = '';
            rightContainer.innerHTML = '';

            // Loop over the first 4 sermons in the JSON data
            sortedSermons.slice(0, 8).forEach((sermon, index) => {

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
            const sortedSermons = [...sermons].sort((a, b) => {
                const aDate = new Date(a.date);
                const bDate = new Date(b.date);
                const aTime = Number.isNaN(aDate.getTime()) ? 0 : aDate.getTime();
                const bTime = Number.isNaN(bDate.getTime()) ? 0 : bDate.getTime();
                return bTime - aTime;
            });
    
            // Select the .cn-slider container in .cat-news
            const cnSliderContainer = document.querySelector(".cat-news .cn-slider");
    
            // Clear any existing content in the container
            cnSliderContainer.innerHTML = '';
    
            // Loop over the 9th to 20th items (index 8 to 19) in the JSON data
            sortedSermons.slice(8, 18).forEach((sermon) => {
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
        const mainNewsContainer = document.querySelector(".main-news .container");
        if (!mainNewsContainer) {
            return;
        }

        try {
            const response = await fetch('latest_sermons.json');
            const sermons = await response.json();

            const parseLengthSeconds = (sermon) => {
                const directSeconds = Number(
                    sermon.length_seconds ?? sermon.duration_seconds ?? sermon.video_length_seconds
                );
                if (!Number.isNaN(directSeconds) && directSeconds > 0) {
                    return directSeconds;
                }

                const textLength = sermon.length ?? sermon.duration ?? sermon.video_length;
                if (typeof textLength === "string") {
                    const parts = textLength.split(":").map((part) => Number(part));
                    if (parts.length === 2 && parts.every((part) => !Number.isNaN(part))) {
                        return (parts[0] * 60) + parts[1];
                    }
                    if (parts.length === 3 && parts.every((part) => !Number.isNaN(part))) {
                        return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
                    }
                }
                return 0;
            };

            const formatLength = (seconds) => {
                if (!seconds || seconds <= 0) {
                    return "N/A";
                }
                const hrs = Math.floor(seconds / 3600);
                const mins = Math.floor((seconds % 3600) / 60);
                const secs = seconds % 60;
                if (hrs > 0) {
                    return `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
                }
                return `${mins}:${String(secs).padStart(2, "0")}`;
            };

            const enhancedSermons = sermons.map((sermon) => {
                const parsedDate = new Date(sermon.date);
                return {
                    ...sermon,
                    _parsedDate: parsedDate,
                    _dateText: sermon.date || "",
                    _lengthSeconds: parseLengthSeconds(sermon),
                    tags: Array.isArray(sermon.tags) ? sermon.tags : []
                };
            });

            const allTags = [...new Set(
                enhancedSermons.flatMap((sermon) => sermon.tags)
            )].sort((a, b) => a.localeCompare(b));

            mainNewsContainer.innerHTML = '';

            const controlsRow = document.createElement("div");
            controlsRow.className = "library-controls row align-items-end mb-4";

            const searchCol = document.createElement("div");
            searchCol.className = "col-md-6 mb-3";
            const searchInput = document.createElement("input");
            searchInput.type = "text";
            searchInput.className = "form-control";
            searchInput.placeholder = "Search by title, date, or tags";
            searchCol.appendChild(searchInput);

            const tagFilterCol = document.createElement("div");
            tagFilterCol.className = "col-md-2 mb-3";
            const tagFilterSelect = document.createElement("select");
            tagFilterSelect.className = "form-control";
            const allTagsOption = document.createElement("option");
            allTagsOption.value = "";
            allTagsOption.textContent = "All Tags";
            tagFilterSelect.appendChild(allTagsOption);
            allTags.forEach((tag) => {
                const option = document.createElement("option");
                option.value = tag;
                option.textContent = tag;
                tagFilterSelect.appendChild(option);
            });
            tagFilterCol.appendChild(tagFilterSelect);

            const sortFieldCol = document.createElement("div");
            sortFieldCol.className = "col-md-2 mb-3";
            const sortFieldSelect = document.createElement("select");
            sortFieldSelect.className = "form-control";
            [
                { value: "date", label: "Sort: Date" },
                { value: "name", label: "Sort: Name" },
                { value: "length", label: "Sort: Length" }
            ].forEach((item) => {
                const option = document.createElement("option");
                option.value = item.value;
                option.textContent = item.label;
                sortFieldSelect.appendChild(option);
            });
            sortFieldCol.appendChild(sortFieldSelect);

            const sortOrderCol = document.createElement("div");
            sortOrderCol.className = "col-md-2 mb-3";
            const sortOrderSelect = document.createElement("select");
            sortOrderSelect.className = "form-control";
            [
                { value: "desc", label: "Desc" },
                { value: "asc", label: "Asc" }
            ].forEach((item) => {
                const option = document.createElement("option");
                option.value = item.value;
                option.textContent = item.label;
                sortOrderSelect.appendChild(option);
            });
            sortOrderCol.appendChild(sortOrderSelect);

            controlsRow.appendChild(searchCol);
            controlsRow.appendChild(tagFilterCol);
            controlsRow.appendChild(sortFieldCol);
            controlsRow.appendChild(sortOrderCol);
            mainNewsContainer.appendChild(controlsRow);

            const resultsInfo = document.createElement("p");
            resultsInfo.className = "library-results-count mb-3";
            mainNewsContainer.appendChild(resultsInfo);

            const resultsGrid = document.createElement("div");
            resultsGrid.className = "library-results";
            mainNewsContainer.appendChild(resultsGrid);

            const renderResults = () => {
                const searchTerm = searchInput.value.trim().toLowerCase();
                const selectedTag = tagFilterSelect.value;
                const sortField = sortFieldSelect.value;
                const sortOrder = sortOrderSelect.value;
                const sortMultiplier = sortOrder === "asc" ? 1 : -1;

                const filtered = enhancedSermons.filter((sermon) => {
                    const tagsText = sermon.tags.join(" ").toLowerCase();
                    const matchesSearch = !searchTerm
                        || sermon.title.toLowerCase().includes(searchTerm)
                        || sermon._dateText.toLowerCase().includes(searchTerm)
                        || tagsText.includes(searchTerm);

                    const matchesTag = !selectedTag || sermon.tags.includes(selectedTag);
                    return matchesSearch && matchesTag;
                });

                filtered.sort((a, b) => {
                    if (sortField === "name") {
                        return a.title.localeCompare(b.title) * sortMultiplier;
                    }
                    if (sortField === "length") {
                        return (a._lengthSeconds - b._lengthSeconds) * sortMultiplier;
                    }
                    return (a._parsedDate - b._parsedDate) * sortMultiplier;
                });

                resultsGrid.innerHTML = '';
                resultsInfo.textContent = `${filtered.length} sermon${filtered.length === 1 ? "" : "s"} shown`;

                const buildSermonCard = (sermon) => {
                    const col = document.createElement("div");
                    col.className = "col-md-3";

                    const cardLink = document.createElement("a");
                    cardLink.className = "mn-card-link";
                    cardLink.href = sermon.summary_link;

                    const mnImgDiv = document.createElement("div");
                    mnImgDiv.className = "mn-img";

                    const img = document.createElement("img");
                    img.src = sermon.thumbnail_url;
                    img.alt = `Thumbnail for ${sermon.title}`;

                    const titleDiv = document.createElement("div");
                    titleDiv.className = "mn-title";

                    const titleText = document.createElement("span");
                    titleText.textContent = sermon.title;

                    titleDiv.appendChild(titleText);
                    mnImgDiv.appendChild(img);
                    mnImgDiv.appendChild(titleDiv);
                    cardLink.appendChild(mnImgDiv);

                    const metaDiv = document.createElement("div");
                    metaDiv.className = "mn-meta mt-2";
                    metaDiv.textContent = `${sermon._dateText}  |  ${formatLength(sermon._lengthSeconds)}`;

                    const tagsDiv = document.createElement("div");
                    tagsDiv.className = "mn-tags mt-2";
                    sermon.tags.forEach((tag) => {
                        const tagButton = document.createElement("button");
                        tagButton.type = "button";
                        tagButton.className = "badge badge-primary mr-2 mb-1 border-0";
                        tagButton.textContent = tag;
                        tagButton.addEventListener("click", (event) => {
                            event.preventDefault();
                            tagFilterSelect.value = tag;
                            renderResults();
                        });
                        tagsDiv.appendChild(tagButton);
                    });

                    col.appendChild(cardLink);
                    col.appendChild(metaDiv);
                    col.appendChild(tagsDiv);
                    return col;
                };

                if (sortField === "date") {
                    let currentYear = null;
                    let currentMonth = null;
                    let monthRow = null;

                    filtered.forEach((sermon) => {
                        const sermonDate = sermon._parsedDate;
                        const yearLabel = Number.isNaN(sermonDate.getTime())
                            ? (sermon._dateText.slice(0, 4) || "Unknown Year")
                            : String(sermonDate.getFullYear());
                        const monthLabel = Number.isNaN(sermonDate.getTime())
                            ? "Unknown Month"
                            : sermonDate.toLocaleString('default', { month: 'long' });

                        if (yearLabel !== currentYear) {
                            currentYear = yearLabel;
                            currentMonth = null;

                            const yearHeader = document.createElement("h2");
                            yearHeader.textContent = yearLabel;
                            resultsGrid.appendChild(yearHeader);
                        }

                        if (monthLabel !== currentMonth) {
                            currentMonth = monthLabel;

                            const monthHeader = document.createElement("h3");
                            monthHeader.textContent = monthLabel;
                            resultsGrid.appendChild(monthHeader);

                            monthRow = document.createElement("div");
                            monthRow.className = "row";
                            resultsGrid.appendChild(monthRow);
                        }

                        monthRow.appendChild(buildSermonCard(sermon));
                    });
                    return;
                }

                const flatRow = document.createElement("div");
                flatRow.className = "row";
                filtered.forEach((sermon) => {
                    flatRow.appendChild(buildSermonCard(sermon));
                });
                resultsGrid.appendChild(flatRow);
            };

            [searchInput, tagFilterSelect, sortFieldSelect, sortOrderSelect].forEach((element) => {
                element.addEventListener("input", renderResults);
                element.addEventListener("change", renderResults);
            });

            renderResults();
        } catch (error) {
            console.error("Error loading main news items:", error);
        }
    }
    
    // Call the function on document ready
    $(document).ready(function () {
        loadMainNews();
    });

    // Video page title/date header under the embedded video
    async function injectVideoHeader() {
        const videoFrame = document.getElementById("videoFrame");
        if (!videoFrame) {
            return;
        }

        const pathParts = window.location.pathname.split("/");
        const sermonFolder = pathParts[pathParts.length - 2] || "";
        if (!sermonFolder || !sermonFolder.includes("_")) {
            return;
        }

        const videoWrapper = videoFrame.closest(".col-md-12");
        if (!videoWrapper || videoWrapper.querySelector(".video-page-header")) {
            return;
        }

        const folderDate = sermonFolder.split("_")[0] || "";
        const fallbackDate = /^\d{4}-\d{2}-\d{2}$/.test(folderDate) ? folderDate : "";

        try {
            const response = await fetch("../../latest_sermons.json");
            if (!response.ok) {
                throw new Error("Could not load latest sermons");
            }

            const sermons = await response.json();
            const expectedLink = `sermons/${sermonFolder}/video.html`;
            const match = sermons.find((sermon) => sermon.summary_link === expectedLink);

            const title = match?.title || "Sermon";
            const rawDate = match?.date || fallbackDate;
            let formattedDate = rawDate;
            const parsedDate = new Date(rawDate);
            if (!Number.isNaN(parsedDate.getTime())) {
                formattedDate = parsedDate.toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric"
                });
            }

            const headerWrap = document.createElement("div");
            headerWrap.className = "video-page-header mt-3";

            const titleEl = document.createElement("h3");
            titleEl.textContent = title;
            headerWrap.appendChild(titleEl);

            const dateEl = document.createElement("p");
            dateEl.className = "mn-meta mb-0";
            dateEl.textContent = formattedDate || "";
            headerWrap.appendChild(dateEl);

            videoWrapper.appendChild(headerWrap);
        } catch (error) {
            console.error("Error loading video header:", error);
        }
    }

    injectVideoHeader();

    // Footer normalization across pages
    const currentYear = new Date().getFullYear();
    const footerCopyright = document.querySelector(".footer-bottom .copyright p");
    if (footerCopyright) {
        footerCopyright.textContent = `${currentYear}\u00A9 Powered by jocal AI`;
    }

    const footerTemplateBy = document.querySelector(".footer-bottom .template-by p");
    if (footerTemplateBy) {
        footerTemplateBy.textContent = "All Rights Reserved by jocal.dev";
    }
    

})(jQuery);

