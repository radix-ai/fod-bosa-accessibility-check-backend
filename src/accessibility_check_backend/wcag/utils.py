"""Handy functions."""

from collections import Counter
from pathlib import Path
from typing import List

import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from .type_aliases import Image, RGBColor


def calculate_contrast_ratio(color1: RGBColor, color2: RGBColor) -> float:
    """Calculate the contrast ratio between 2 colors.

    Based on https://www.w3.org/WAI/WCAG21/Techniques/general/G145.

    Parameters
    ----------
    color1 : np.array
        The first color
    color2 : np.array
        The second color

    Returns
    -------
    float
        The contrast ratio between the two given colors
    """
    light = color1 if np.sum(color1) > np.sum(color2) else color2
    dark = color1 if np.sum(color1) < np.sum(color2) else color2

    def linearize(rgb_value: float) -> float:
        """Linearize a gamma-compressed RGB value.

        Parameters
        ----------
        rgb_value : float
            A gamma-compressed RGB value (0-255)

        Returns
        -------
        float
            A linear RGB value (0.0-1.0)
        """
        index = rgb_value / 255.0
        if index < 0.03928:
            return index / 12.92
        else:
            return ((index + 0.055) / 1.055) ** 2.4

    def relative_luminance(rgb: RGBColor) -> float:
        """Calculate the relative luminance of a color.

        https://en.wikipedia.org/wiki/Relative_luminance.

        Parameters
        ----------
        rgb : np.array
            An RGB color, represented as 3 values between 0 and 255

        Returns
        -------
        float
            The relative luminance of the given color
        """
        return 0.2126 * linearize(rgb[0]) + 0.7152 * linearize(rgb[1]) + 0.0722 * linearize(rgb[2])

    return (relative_luminance(light) + 0.05) / (relative_luminance(dark) + 0.05)


def most_common_colors(a: Image) -> List[RGBColor]:
    """Identify the two most common colors in part of an image."""
    a = a.reshape(
        a.shape[0] * a.shape[1], 3
    )  # Flatten the image into one big list of [R,G,B] arrays
    a = [tuple(v) for v in a]  # Convert them to tuples so they are hashable
    c = Counter(a)  # type: ignore
    colors = [v[0] for v in c.most_common(2)]  # Pick two most common
    if len(colors) < 2:  # Handle edge case where there is only one color
        colors += [None] * (2 - len(colors))
    return colors


def get_contrast_ratio(img: Image, x1: int, x2: int, y1: int, y2: int) -> float:
    """Compute the contrast ratio of a word vs background at the specicied coordinates.

    Parameters
    ----------
    img : Image
        A screenshot of a web page
    x1 : int
        The x value of the top-left corner of the word's bounding box
    x2 : int
        The y value of the bottom-right corner of the word's bounding box
    y1 : int
        The x value of the top-left corner of the word's bounding box
    y2 : int
        The y value of the bottom-right corner of the word's bounding box

    Returns
    -------
    float
        The contrast ratio of the word against its background
    """
    # Get the subimages of the letter, the top border and the bottom border
    word = img[y1:y2, x1:x2]
    top_border = img[y1 - 3 : y1, x1:x2]
    bottom_border = img[y2 : y2 + 3, x1:x2]

    # Get 2 most frequent colors inside the bounding box
    most_common_color, second_most_common_color = most_common_colors(word)

    # Get the contrast ratio between these colors
    if second_most_common_color is not None:
        contrast_1 = calculate_contrast_ratio(most_common_color, second_most_common_color)
    else:
        contrast_1 = -1

    # Get the average color of the pixels right above and below the bounding box
    color_above = top_border.mean(axis=0).mean(axis=0)
    color_below = bottom_border.mean(axis=0).mean(axis=0)
    border_color = np.vstack([color_above, color_below]).mean(axis=0)

    # Calculate the contrast between the border and the two most frequent colors
    if most_common_color is not None:
        contrast_2 = calculate_contrast_ratio(border_color, most_common_color)
    else:
        contrast_2 = -1

    if second_most_common_color is not None:
        contrast_3 = calculate_contrast_ratio(border_color, second_most_common_color)
    else:
        contrast_3 = -1

    # The actual contrast is the maximum value of these two contrasts
    return max(contrast_1, contrast_2, contrast_3)


def take_screenshot(
    url: str, window_width: int, window_height: int, path: Path, scale: int
) -> WebDriver:
    """Render the given URL, take a screenshot, and save to the given path.

    Note: We return the web driver used to take the screenshot so we can use it later on.

    Parameters
    ----------
    url : str
        The URL of the web page to take a screenshot of
    window_width : int
        The window width the web driver should have
    window_height : int
        The window height the web driver should have
    path : Path
        The path where the screenshot will be stored
    scale : int
        The scale factor for which the screenshot should be taken

    Returns
    -------
    WebDriver
        The web driver used to take the screenshot
    """
    # Instantiate a chrome options object so you can set the size and headless preference
    chrome_options = webdriver.chrome.options.Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument(f"--window-size={window_width}x{window_height}")
    chrome_options.add_argument(f"--force-device-scale-factor={scale}")
    chrome_options.add_argument("--no-sandbox")  # TODO: check whether we can remove this
    chrome_options.add_argument("--disable-dev-shm-usage")  # TODO: check whether we can remove this

    # Start the web driver
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)

    # Take a screenshot (https://stackoverflow.com/a/52572919)
    original_size = driver.get_window_size()
    required_height = driver.execute_script("return document.body.parentNode.scrollHeight")
    driver.set_window_size(original_size["width"], required_height)
    driver.save_screenshot(str(path))
    return driver


def get_xpath_of_element(element: WebElement, current_xpath: str = "") -> str:
    """Return the xpath of a DOM element in a recursive way.

    Parameters
    ----------
    element : WebElement
        The DOM element for which we need the xpath
    current_xpath : str, optional
        The xpath of the DOM's child, by default ""

    Returns
    -------
    str
        The xpath of the DOM element
    """
    # If the current element is html, we have reached the root element and recursion stops
    if element.tag_name == "html":
        return "/html[1]" + current_xpath

    # Define the parent of the element
    parent = element.find_element_by_xpath("..")

    # Define all children of the parent (i.e. the element's siblings and the element itself)
    children = parent.find_elements_by_xpath("*")

    # Define the index of the element amongst its siblings with the same tag
    count = 0
    for child in children:
        if element.tag_name == child.tag_name:
            count += 1
        if element == child:
            # Once the element is found amongst its siblings, add a new prefix to the current xpath
            new_prefix = "/" + element.tag_name + "[" + str(count) + "]"
            # Get the xpath of the parent
            return get_xpath_of_element(parent, new_prefix + current_xpath)
    return ""  # This should never be reached