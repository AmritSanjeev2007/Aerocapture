""" The main entry point into the program. """

from display.renderer import ( Renderer )

if __name__ == "__main__":

    renderer = Renderer()
    renderer.render()
    renderer.destroy()

