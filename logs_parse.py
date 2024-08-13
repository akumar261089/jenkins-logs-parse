def analyze_jenkins_log(log_text):
    sections = {
        "start": "",
        "stages": {},
        "end": ""
    }

    current_stage = None
    is_stage_active = False
    stage_start_pattern = re.compile(r'\[Pipeline\] \{ \((.*?)\)')
    stage_end_pattern = re.compile(r'\[Pipeline\] \}\n')

    lines = log_text.splitlines()
    for line in lines:
        # Check for the start of the pipeline
        if "[Pipeline] Start of Pipeline" in line:
            sections["start"] = line
            continue

        # Check for stage start
        stage_start_match = stage_start_pattern.search(line)
        if stage_start_match:
            current_stage = stage_start_match.group(1)
            sections["stages"][current_stage] = []
            is_stage_active = True
            continue

        # Check for stage end
        if stage_end_pattern.match(line):
            is_stage_active = False
            current_stage = None
            continue

        # If inside a stage, add lines to the current stage
        if is_stage_active and current_stage:
            sections["stages"][current_stage].append(line)
            continue

        # Capture any remaining lines as part of the end section
        if not current_stage:
            sections["end"] += line + "\n"

    return sections