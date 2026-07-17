fetch("/api/forecast-data")
    .then(r => r.json())
    .then(data => {

        if (!data.has_enough_data) {
            document.getElementById("forecast-empty-state").style.display = "block";
            document.getElementById("forecast-chart-wrapper").style.display = "none";
            document.getElementById("forecast-chart-wrapper-wind").style.display = "none";
            return;
        }

        const layout = (title) => ({
            title: { text: title, font: { color: "#F8FAFC", size: 14 } },
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#94A3B8" },
            margin: { t: 30, l: 50, r: 20, b: 40 },
            xaxis: { gridcolor: "#263A5B" },
            yaxis: { gridcolor: "#263A5B" },
            legend: { orientation: "h", y: -0.2 }
        });

        Plotly.newPlot("chart-forecast-demand", [
            {
                x: data.demand_actual.timestamps, y: data.demand_actual.values,
                name: "Actual demand (MW)", type: "scatter", mode: "lines",
                line: { color: "#00E5A8", width: 2 }
            },
            {
                x: data.demand_projected.timestamps, y: data.demand_projected.values,
                name: "Projected", type: "scatter", mode: "lines",
                line: { color: "#00E5A8", width: 2, dash: "dot" }
            }
        ], layout("System Demand: Actual vs Projected"), { responsive: true, displayModeBar: false });

        Plotly.newPlot("chart-forecast-wind", [
            {
                x: data.wind_actual.timestamps, y: data.wind_actual.values,
                name: "Actual wind (MW)", type: "scatter", mode: "lines",
                line: { color: "#4EA3FF", width: 2 }
            },
            {
                x: data.wind_projected.timestamps, y: data.wind_projected.values,
                name: "Projected", type: "scatter", mode: "lines",
                line: { color: "#4EA3FF", width: 2, dash: "dot" }
            }
        ], layout("Wind Generation: Actual vs Projected"), { responsive: true, displayModeBar: false });

    })
    .catch(err => console.error("Forecast data error:", err));
