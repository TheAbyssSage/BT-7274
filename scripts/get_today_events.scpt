tell application "Calendar"
    set startDate to current date
    set startDate to startDate - (time of startDate)
    set endDate to startDate + (1 * days)
    
    set eventList to {}
    repeat with cal in calendars
        try
            set calEvents to (every event of cal whose start date ≥ startDate and start date < endDate)
            repeat with evt in calEvents
                try
                    set evtName to name of evt
                    set evtStart to start date of evt
                    set end of eventList to evtName & " at " & evtStart
                end try
            end repeat
        end try
    end repeat
    
    if length of eventList is 0 then
        return "No events today."
    else
        set AppleScript's text item delimiters to "\n"
        return eventList as string
    end if
end tell
