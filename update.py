import subprocess

def git_push(commit_message="Auto-commit generated data"):
    user = "tastypork"
    sudo_user = ["sudo", "-u", user]
    paths_to_stage = ["html/sermon", "html/latest_sermons.json"]

    try:
        # Stage changes in specified paths as tastypork user
        subprocess.run(sudo_user + ["git", "add"] + paths_to_stage, check=True)
        
        # Commit changes with the provided commit message as tastypork user
        subprocess.run(sudo_user + ["git", "commit", "-m", commit_message], check=True)
        
        # Push to the remote repository as tastypork user
        subprocess.run(sudo_user + ["git", "push"], check=True)
        
        print("Changes committed and pushed successfully.")
    except subprocess.CalledProcessError as e:
        print("An error occurred:", e)