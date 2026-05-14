tell application "Calendar"
    set startDate to current date
    set startDate to startDate + (17 * days)
    set startDate to startDate - (time of startDate)
    set endDate to startDate + (30 * days)
    
    set eventList to {}
    repeat with cal in calendars
        try
            set calEvents to (every event of cal whose start date ≥ startDate and start date < endDate)
            repeat with evt in calEvents
                try
                    set evtName to name of evt
                    set evtStart to start date of evt
                    set evtEnd to end date of evt
                    set evtLoc to location of evt
                    if evtLoc is missing value then set evtLoc to ""
                    set calName to name of cal
                    set eventInfo to evtName & "|" & evtStart & "|" & evtEnd & "|" & evtLoc & "|" & calName
                    set end of eventList to eventInfo
                on error
                    -- Skip events that can't be read
                end try
            end repeat
        on error
            -- Skip calendars that can't be read
        end try
    end repeat
    
    if length of eventList is 0 then
        return "No events found for next month."
    else
        set AppleScript's text item delimiters to "\n"
        return eventList as string
    end if
end tell
