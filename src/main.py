"""Alternative entry point for direct development execution."""

from importlib import import_module

main = import_module("1hack_amethyst").main


if __name__ == "__main__":
    main()
