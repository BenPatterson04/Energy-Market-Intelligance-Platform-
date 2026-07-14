// ======================================
// GridWise Dashboard
// Auto Refresh
// ======================================

function refreshDashboard() {

    console.log("Refreshing GridWise...");

    fetch(window.location.href, {
        cache: "no-store"
    })

    .then(response => response.text())

    .then(html => {

        const parser = new DOMParser();

        const documentNew = parser.parseFromString(html, "text/html");

        const dashboard = document.querySelector(".dashboard");

        const dashboardNew = documentNew.querySelector(".dashboard");

        if (dashboard && dashboardNew) {

            dashboard.innerHTML = dashboardNew.innerHTML;

            console.log("Dashboard Updated");

        }

    })

    .catch(error => {

        console.error("Refresh failed:", error);

    });

}


// Refresh every 5 minutes

setInterval(refreshDashboard, 300000);


// Uncomment for testing every 30 seconds

// setInterval(refreshDashboard, 30000);