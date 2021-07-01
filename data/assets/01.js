// getDataTimestamp returns test results timestamp from domDateTimeElement's title
function getDataTimestamp(domDateTimeElement) {
    const isoDateTimeStr =  domDateTimeElement.title;
    return new Date(isoDateTimeStr);
}

// checkIfServerDataIsStale makes header-stale-data-warning visible if server data is stale.
function checkIfServerDataIsStale() {
    const domDateTimeElement = document.getElementById('current-timestamp');
    const domDiffWarningElement = document.getElementById('timeinterval');
    if (domDateTimeElement) {
        const serverData = getDataTimestamp(domDateTimeElement);
        const dateNow = new Date();
        const dataAgeSeconds = (dateNow.getTime() - serverData.getTime()) / 1000; 
        const allowedDataAgeSeconds = domDiffWarningElement.innerText;
        const warningElement = document.getElementsByClassName('header-stale-data-warning');
        if(warningElement[0]) {
            if(dataAgeSeconds > parseInt(allowedDataAgeSeconds)) {
                warningElement[0].className = 'header-stale-data-warning header-stale-data-warning-visible';
            } else{
               warningElement[0].className = 'header-stale-data-warning';
            }
        }
    }
    setTimeout(checkIfServerDataIsStale, 100);
}
setTimeout(checkIfServerDataIsStale, 100);


// setLastUpdatedToLocalTime sets LastUpdated label to client's local time
function setLastUpdatedToLocalTime() {
    var domDateTimeElement = document.getElementById('current-timestamp');
    if (domDateTimeElement) {
        const serverData = getDataTimestamp(domDateTimeElement);
        domDateTimeElement.textContent = serverData.toLocaleString()
        return
    }
    setTimeout(setLastUpdatedToLocalTime, 100)
}
setTimeout(setLastUpdatedToLocalTime, 100)