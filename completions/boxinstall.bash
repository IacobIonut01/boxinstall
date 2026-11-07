# bash completion for boxinstall
_boxinstall() {
	local cur prev opts
	COMPREPLY=()
	cur="${COMP_WORDS[COMP_CWORD]}"
	prev="${COMP_WORDS[COMP_CWORD-1]}"

	opts="--help --version --pick --no-gui --no-desktop --box --dry-run --verbose"

	case "$prev" in
	--box)
		# propose existing distrobox containers
		if command -v distrobox >/dev/null 2>&1; then
			mapfile -t COMPREPLY < <(distrobox list --no-color 2>/dev/null | awk -F'|' 'NR>1 {gsub(/^ +| +$/, "", $2); if ($2 != "") print $2}')
		fi
		return 0
		;;
	esac

	if [[ "$cur" == -* ]]; then
		mapfile -t COMPREPLY < <(compgen -W "$opts" -- "$cur")
	else
		mapfile -t COMPREPLY < <(compgen -f -- "$cur")
	fi
}

complete -F _boxinstall boxinstall
