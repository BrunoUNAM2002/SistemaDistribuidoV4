"""
Animation Effects - Wrappers for TerminalTextEffects
Provides integration between TTE and Textual widgets
"""

from terminaltexteffects.effects import effect_slide, effect_print, effect_beams
from terminaltexteffects.utils.terminal import Terminal
from terminaltexteffects.utils.graphics import Color, Gradient
from typing import Iterator
import asyncio


class TTEWrapper:
    """
    Wrapper to integrate TerminalTextEffects with Textual
    Converts TTE animations to renderable frames
    """
    
    @staticmethod
    def slide_effect(text: str, direction: str = "diagonal") -> Iterator[str]:
        """
        Slide effect - text slides into view
        
        Args:
            text: Text to animate
            direction: "diagonal", "horizontal", "vertical"
        
        Yields:
            Each frame of the animation as a string
        """
        # Create effect instance
        effect = effect_slide.Slide(text)
        
        # Configure effect
        effect.effect_config.merge = True
        effect.effect_config.movement_speed = 0.5
        effect.effect_config.grouping = "row"  # Animate by row
        
        # Direction mapping
        direction_map = {
            "diagonal": effect_slide.SlideDirection.DIAGONAL,
            "horizontal": effect_slide.SlideDirection.HORIZONTAL,
            "vertical": effect_slide.SlideDirection.VERTICAL,
        }
        effect.effect_config.direction = direction_map.get(direction, effect_slide.SlideDirection.DIAGONAL)
        
        # Generate frames
        with effect.terminal_output() as terminal:
            for frame in effect:
                yield frame
    
    @staticmethod
    def typewriter_effect(text: str, typing_speed: int = 2) -> Iterator[str]:
        """
        Typewriter effect - text appears letter by letter
        
        Args:
            text: Text to animate
            typing_speed: Characters per frame
        
        Yields:
            Each frame of the animation as a string
        """
        effect = effect_print.Print(text)
        
        # Configure typing speed
        effect.effect_config.print_speed = typing_speed
        effect.effect_config.print_head_return_speed = 1.0
        
        # Generate frames
        with effect.terminal_output() as terminal:
            for frame in effect:
                yield frame
    
    @staticmethod
    def beam_effect(text: str, beam_color: str = "cyan") -> Iterator[str]:
        """
        Beam effect - beams of light converge to reveal text
        
        Args:
            text: Text to animate
            beam_color: Color of the beams
        
        Yields:
            Each frame of the animation as a string
        """
        effect = effect_beams.Beams(text)
        
        # Configure beams
        effect.effect_config.beam_delay = 10
        effect.effect_config.beam_row_symbols = "▂▄▆█"
        effect.effect_config.beam_column_symbols = "▌▐█"
        
        # Set colors based on parameter
        color_map = {
            "cyan": Color("00D9FF"),
            "green": Color("00FF00"),
            "blue": Color("0077BE"),
            "magenta": Color("FF00FF"),
            "yellow": Color("FFFF00"),
        }
        beam_gradient = Gradient(color_map.get(beam_color, Color("00D9FF")), 10)
        effect.effect_config.beam_gradient = beam_gradient
        
        # Generate frames
        with effect.terminal_output() as terminal:
            for frame in effect:
                yield frame


class SimpleAnimations:
    """
    Simple custom animations without TTE (lighter weight)
    """
    
    @staticmethod
    def pulse(text: str, count: int = 3) -> Iterator[str]:
        """
        Simple pulse animation - text fades in/out
        
        Args:
            text: Text to pulse
            count: Number of pulses
        
        Yields:
            Each frame as styled rich text
        """
        from rich.text import Text
        
        for _ in range(count):
            # Fade in
            for alpha in range(0, 101, 10):
                styled = Text(text, style=f"dim" if alpha < 50 else "bold")
                yield styled
                
            # Fade out
            for alpha in range(100, -1, -10):
                styled = Text(text, style=f"dim" if alpha < 50 else "bold")
                yield styled
    
    @staticmethod
    def spinner(frames: int = 10) -> Iterator[str]:
        """
        Spinning loader animation
        
        Args:
            frames: Number of frames to generate
        
        Yields:
            Each spinner frame
        """
        spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        
        for i in range(frames):
            yield spinners[i % len(spinners)]
    
    @staticmethod
    def progress_dots(text: str, max_dots: int = 3) -> Iterator[str]:
        """
        Progress dots animation: "Loading", "Loading.", "Loading..", "Loading..."
        
        Args:
            text: Base text
            max_dots: Maximum number of dots
        
        Yields:
            Text with animated dots
        """
        import itertools
        
        for dots in itertools.cycle(range(max_dots + 1)):
            yield f"{text}{'.' * dots}"


# Export key classes
__all__ = [
    'TTEWrapper',
    'SimpleAnimations',
]
