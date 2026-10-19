(function () {
    "use strict";

    var rideData = document.getElementById("ride-data");
    if (!rideData) return;

    var rideId = rideData.getAttribute("data-ride-id");
    if (!rideId) return;

    var statusEl = document.getElementById("ride-status");
    var announcer = document.getElementById("live-announcer");
    var btnPause = document.getElementById("btn-pause");
    var btnResume = document.getElementById("btn-resume");
    var btnStop = document.getElementById("btn-stop");

    var updateCount = 0;

    // Format seconds as M:SS or H:MM:SS
    function formatDuration(seconds) {
        var s = Math.floor(seconds);
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        var sec = s % 60;
        var secStr = sec < 10 ? "0" + sec : "" + sec;
        if (h > 0) {
            var minStr = m < 10 ? "0" + m : "" + m;
            return h + ":" + minStr + ":" + secStr;
        }
        return m + ":" + secStr;
    }

    // Update a single element's text
    function setText(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    // SSE connection
    var source = new EventSource("/api/rides/" + rideId + "/live");

    source.addEventListener("sample", function (e) {
        var data = JSON.parse(e.data);
        var sample = data.sample || {};
        var stats = data.stats || {};

        setText("live-power", (sample.power || 0) + " W");
        setText("live-speed", ((sample.speed || 0) * 3.6).toFixed(1) + " km/h");
        setText("live-cadence", (sample.cadence || 0) + " rpm");
        setText("live-heart-rate", (sample.heart_rate || 0) + " bpm");
        setText("live-distance", ((sample.distance || 0) / 1000).toFixed(2) + " km");
        setText("live-duration", formatDuration(stats.duration || 0));
        setText("live-avg-power", (stats.avg_power || 0) + " W");
        setText("live-avg-speed", ((stats.avg_speed || 0) * 3.6).toFixed(1) + " km/h");

        updateCount++;

        // Announce to screen readers every 10th update
        if (announcer && updateCount % 10 === 0) {
            announcer.textContent =
                (sample.power || 0) + " watts, " +
                ((sample.speed || 0) * 3.6).toFixed(0) + " km/h, " +
                ((sample.distance || 0) / 1000).toFixed(1) + " km covered";
        }
    });

    source.addEventListener("completed", function () {
        source.close();
        if (statusEl) statusEl.innerHTML = "Status: <strong>completed</strong>";
        if (announcer) announcer.textContent = "Ride completed.";
        setTimeout(function () {
            window.location.reload();
        }, 1000);
    });

    source.onerror = function () {
        // SSE will auto-reconnect for transient errors.
        // If the ride is done, the server closes the connection.
    };

    // Ride control buttons
    function rideAction(action) {
        var method = "PATCH";
        var url = "/api/rides/" + rideId + "/" + action;

        fetch(url, { method: method })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (statusEl) {
                    statusEl.innerHTML = "Status: <strong>" + (data.status || action) + "</strong>";
                }
                if (action === "pause") {
                    btnPause.hidden = true;
                    btnResume.hidden = false;
                    if (announcer) announcer.textContent = "Ride paused.";
                } else if (action === "resume") {
                    btnResume.hidden = true;
                    btnPause.hidden = false;
                    if (announcer) announcer.textContent = "Ride resumed.";
                } else if (action === "stop") {
                    source.close();
                    if (announcer) announcer.textContent = "Ride stopped.";
                    setTimeout(function () {
                        window.location.reload();
                    }, 1000);
                }
            });
    }

    if (btnPause) {
        btnPause.addEventListener("click", function () { rideAction("pause"); });
    }
    if (btnResume) {
        btnResume.addEventListener("click", function () { rideAction("resume"); });
    }
    if (btnStop) {
        btnStop.addEventListener("click", function () { rideAction("stop"); });
    }
})();
