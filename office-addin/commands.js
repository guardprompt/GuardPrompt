/* Function file. The task-pane buttons use ShowTaskpane (declarative, no code), so this
 * only needs to satisfy Office's FunctionFile load + register the ready handler. Add
 * ExecuteFunction commands here later if you want ribbon buttons that act without opening
 * the pane (e.g. a one-click "Anonymize selection"). */
Office.onReady(() => {});

// Example for later — a ribbon button that runs without the pane:
// function anonymizeSelection(event) { /* Word.run / mailbox.item ... */ event.completed(); }
// if (typeof Office !== "undefined") Office.actions?.associate?.("anonymizeSelection", anonymizeSelection);
