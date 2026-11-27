-- Optional macOS renderer. Export only the requested candidate, then close unsaved.
on run argv
    set requestedFile to POSIX file (item 1 of argv) as alias
    -- A previous open must not supply false evidence for this run.
    tell application "Microsoft PowerPoint" to set existingPaths to full name of every presentation
    if existingPaths is missing value then set existingPaths to {}
    repeat with existingPath in existingPaths
        set existingFile to missing value
        try
            set existingFile to POSIX file (existingPath as text) as alias
        end try
        if existingFile is requestedFile then error "Verification requires a candidate that is not already open."
    end repeat
    -- Open through Launch Services, then wait for this file to become available.
    do shell script "/usr/bin/open -a " & quoted form of "Microsoft PowerPoint" & " " & quoted form of (item 1 of argv)
    set selectedIndex to 0
    repeat 60 times
        tell application "Microsoft PowerPoint" to set deckCount to count of presentations
        repeat with deckIndex from 1 to deckCount
            try
                tell application "Microsoft PowerPoint" to set openedPath to full name of presentation deckIndex
                -- Resolve aliases outside the application tell block.
                set openedFile to POSIX file openedPath as alias
                if openedFile is requestedFile then
                    set selectedIndex to deckIndex as integer
                    exit repeat
                end if
            end try
        end repeat
        if selectedIndex > 0 then exit repeat
        delay 1
    end repeat
    if selectedIndex = 0 then error "Requested file did not open normally; repaired or unrelated presentations are not exported."
    with timeout of 180 seconds
        tell application "Microsoft PowerPoint"
            set p to presentation selectedIndex
            set initiallySaved to saved of p
            if initiallySaved is not true then error "Opened presentation has unsaved changes; do not count it as an unchanged normal open."
            set n to count of slides of p
            set appVersion to version as text
            set readSlides to 0
            repeat with slideIndex from 1 to n
                set objectCount to count of shapes of slide slideIndex of p
                set readSlides to readSlides + 1
            end repeat
            set confirmedPath to full name of p
            set stillSaved to saved of p
        end tell
        set confirmedFile to POSIX file confirmedPath as alias
        if confirmedFile is not requestedFile or stillSaved is not true then error "Presentation changed while reading slides; normal open was not confirmed."
        tell application "Microsoft PowerPoint"
            save p in POSIX file (item 2 of argv) as save as PDF
            close p saving no
            return appVersion & "|" & n & "|saved=true|slides_read=" & readSlides
        end tell
    end timeout
end run
