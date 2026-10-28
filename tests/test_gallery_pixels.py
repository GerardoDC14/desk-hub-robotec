import pathlib
import random
import re
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from gallery_pixels import rect_image_commands, preview_passes


def paint(commands,canvas=None):
    canvas={} if canvas is None else dict(canvas)
    for command in commands:
        match=re.fullmatch(r'fill (\d+),(\d+),(\d+),(\d+),(\d+)',command)
        if match is None: raise AssertionError('Instrucción no válida: '+command)
        x,y,w,h,color=map(int,match.groups())
        if not(0<=x<800 and 0<=y<480 and w>0 and h>0 and x+w<=800 and y+h<=480 and 0<=color<=65535):
            raise AssertionError('Rectángulo fuera del panel: '+command)
        for yy in range(y,y+h):
            for xx in range(x,x+w): canvas[xx,yy]=color
    return canvas


def reference(pixels,cols,rows,x,y,w,h):
    canvas={}
    for row in range(rows):
        top=y+row*h//rows; bottom=y+(row+1)*h//rows
        for column in range(cols):
            left=x+column*w//cols; right=x+(column+1)*w//cols
            for yy in range(max(0,top),min(480,bottom)):
                for xx in range(max(0,left),min(800,right)):
                    canvas[xx,yy]=pixels[row*cols+column]
    return canvas


class RectImageTests(unittest.TestCase):
    def test_solid_image_merges_to_one_native_rectangle(self):
        self.assertEqual(rect_image_commands([123]*80*45,80,45,32,92,528,297),['fill 32,92,528,297,123'])

    def test_horizontal_and_vertical_runs_merge(self):
        pixels=[1,1,2,2,1,1,2,2,3,3,3,3]
        commands=rect_image_commands(pixels,4,3,10,20,40,30)
        self.assertEqual(commands,['fill 10,20,20,20,1','fill 30,20,20,20,2','fill 10,40,40,10,3'])
        self.assertEqual(paint(commands),reference(pixels,4,3,10,20,40,30))

    def test_odd_target_dimensions_have_no_missing_or_overlapping_edges(self):
        pixels=list(range(15))
        commands=rect_image_commands(pixels,5,3,31,93,41,29)
        self.assertEqual(paint(commands),reference(pixels,5,3,31,93,41,29))
        self.assertEqual(len(paint(commands)),41*29)

    def test_non_square_source_preserves_full_rectangular_target(self):
        pixels=list(range(80*45))
        commands=rect_image_commands(pixels,80,45,32,92,53,30)
        self.assertEqual(paint(commands),reference(pixels,80,45,32,92,53,30))
        self.assertEqual(len(paint(commands)),53*30)

    def test_all_display_edges_are_clipped(self):
        for x,y,w,h in [(-5,-9,41,29),(782,466,41,29),(-900,10,41,29),(10,-900,41,29),(800,0,20,20),(0,480,20,20)]:
            with self.subTest(geometry=(x,y,w,h)):
                pixels=list(range(15))
                commands=rect_image_commands(pixels,5,3,x,y,w,h)
                self.assertEqual(paint(commands),reference(pixels,5,3,x,y,w,h))

    def test_zero_size_is_empty_but_negative_size_is_invalid(self):
        self.assertEqual(rect_image_commands([1],1,1,0,0,0,50),[])
        self.assertEqual(rect_image_commands([1],1,1,0,0,50,0),[])
        for w,h in [(-1,10),(10,-1)]:
            with self.assertRaises(ValueError): rect_image_commands([1],1,1,0,0,w,h)

    def test_invalid_grid_colors_and_underlay_are_rejected(self):
        for pixels,cols,rows in [([],0,1),([],1,0),([1],2,1),([65536],1,1),([-1],1,1),(['1'],1,1),([True],1,1),([1],1.5,1)]:
            with self.subTest(values=(pixels,cols,rows)):
                with self.assertRaises(ValueError): rect_image_commands(pixels,cols,rows,0,0,20,20)
        with self.assertRaises(ValueError): rect_image_commands([1],1,1,0,0,20,20,[])
        with self.assertRaises(ValueError): rect_image_commands([1],1,1,0.5,0,20,20)
        with self.assertRaises(ValueError): rect_image_commands([1],1,1,0,0,20,20,[65536])

    def test_identical_underlay_emits_nothing(self):
        pixels=[0,1,2,3,4,5]
        self.assertEqual(rect_image_commands(pixels,3,2,0,0,31,19,pixels),[])

    def test_deltas_reconstruct_image_without_changing_equal_cells(self):
        previous=[1,1,1,2,2,2,1,1,1,2,2,2,3,3,3,4,4,4]
        pixels=[1,8,8,2,2,2,1,8,8,2,2,2,3,3,3,9,9,4]
        base=paint(rect_image_commands(previous,6,3,5,7,49,25))
        changes=rect_image_commands(pixels,6,3,5,7,49,25,previous)
        final=paint(changes,base)
        self.assertEqual(final,reference(pixels,6,3,5,7,49,25))
        changed=paint(changes)
        expected=reference(pixels,6,3,5,7,49,25)
        self.assertTrue(all(base[pos]!=expected[pos] for pos in changed))

    def test_fine_grid_smaller_than_source_still_chooses_correct_visible_cells(self):
        pixels=list(range(63))
        commands=rect_image_commands(pixels,9,7,20,20,4,3)
        self.assertEqual(paint(commands),reference(pixels,9,7,20,20,4,3))

    def test_random_grids_and_underlays_reconstruct(self):
        rng=random.Random(61)
        for _ in range(40):
            cols=rng.randint(1,12); rows=rng.randint(1,10)
            pixels=[rng.randrange(5) for _ in range(cols*rows)]
            underlay=[rng.randrange(5) for _ in pixels]
            geometry=(rng.randint(-7,7),rng.randint(-7,7),rng.randint(1,32),rng.randint(1,26))
            base=paint(rect_image_commands(underlay,cols,rows,*geometry))
            result=paint(rect_image_commands(pixels,cols,rows,*geometry,underlay),base)
            self.assertEqual(result,reference(pixels,cols,rows,*geometry))


class PreviewPassTests(unittest.TestCase):
    def test_gallery_coarse_pass_is_bounded_and_refinement_reconstructs(self):
        pixels=list(range(80*45))
        coarse,fine=preview_passes(pixels,80,45,32,92,528,297)
        self.assertLessEqual(len(coarse),16*9)
        self.assertEqual(len(paint(coarse)),528*297)
        self.assertEqual(paint(fine,paint(coarse)),reference(pixels,80,45,32,92,528,297))
        self.assertTrue(fine)

    def test_uneven_source_buckets_share_exact_edges_with_refinement(self):
        pixels=list(range(37*19))
        coarse,fine=preview_passes(pixels,37,19,-3,17,103,57)
        self.assertLessEqual(len(coarse),16*9)
        self.assertEqual(paint(fine,paint(coarse)),reference(pixels,37,19,-3,17,103,57))

    def test_small_or_solid_images_need_no_refinement(self):
        for cols,rows,pixels in [(3,2,list(range(6))),(80,45,[421]*80*45)]:
            coarse,fine=preview_passes(pixels,cols,rows,32,92,53,30)
            self.assertEqual(fine,[])
            self.assertEqual(paint(coarse),reference(pixels,cols,rows,32,92,53,30))

    def test_empty_target_passes_and_invalid_inputs(self):
        self.assertEqual(preview_passes([1],1,1,0,0,0,20),([],[]))
        with self.assertRaises(ValueError): preview_passes([1],2,1,0,0,20,20)
        with self.assertRaises(ValueError): preview_passes([1],1,1,0,0,20,-1)


if __name__=='__main__': unittest.main()
