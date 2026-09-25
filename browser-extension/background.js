// Open the side panel when the toolbar icon is clicked. That click is also what
// grants `activeTab`, so the panel can read the page the user was looking at.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
