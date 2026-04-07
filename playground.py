from abc import ABC, abstractmethod
from math import pi


class Shape(ABC):
    @abstractmethod
    def area(self):
        pass

    @abstractmethod
    def perimeter(self):
        pass 
    def describe(self):
        print(f"hello I'm{self.__class__.__name__}") 

class Circle(Shape):
    def __init__(self, radious):
        self.radious= radious
    def area (self):
        return pi*self.radious**2
    def perimeter(self):
        return 2*pi*self.radious


class Rectangle(Shape):
    def __init__(self, width, height):
        self.width= width
        self.height=height
    def area (self ):
        return self.width*self.height
    def perimeter(self):
         return 2*(self.width+self.height)

circle1 = Circle(5)

area1 = circle1.area()
radious1 = circle1.radious
print(area1)
print(radious1)
circle1.describe()