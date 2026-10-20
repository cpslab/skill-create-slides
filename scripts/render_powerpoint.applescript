-- Optional macOS renderer. Export only the requested candidate, then close unsaved.
on run argv
    set requestedFile to POSIX file (item 1 of argv) as alias
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
            set n to count of slides of p
            set appVersion to version as text
            save p in POSIX file (item 2 of argv) as save as PDF
            close p saving no
            return appVersion & "|" & n
        end tell
    end timeout
end run
