import { expect, type Locator } from '@playwright/test';

export async function expectSelectionGaps(heading: Locator, before: Locator, after: Locator, afterGap=5) {
  await expect(heading).toBeVisible();
  const bar=(await heading.boundingBox())!,previous=(await before.boundingBox())!,next=(await after.boundingBox())!;
  expect(bar.y-previous.y-previous.height).toBeCloseTo(5,0);
  expect(next.y-bar.y-bar.height).toBeCloseTo(afterGap,0);
  const targetSize = await heading.evaluate(() => matchMedia('(pointer: coarse)').matches ? '44px' : '40px');
  for(const button of await heading.getByRole('button').all()) {
    await expect(button).toHaveCSS('width',targetSize);
    await expect(button).toHaveCSS('height',targetSize);
  }
}

export async function expectSelectionReplacement(heading: Locator, source: Locator) {
  await expect(heading).toBeVisible();
  await expect(source).toBeHidden();
  const original=await source.evaluate(node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width};});
  const bar=(await heading.boundingBox())!;
  expect(bar.x).toBeCloseTo(original.x,0);
  expect(bar.y).toBeCloseTo(original.y,0);
  expect(bar.width).toBeCloseTo(original.width,0);
  const targetSize = await heading.evaluate(() => matchMedia('(pointer: coarse)').matches ? '44px' : '40px');
  for(const button of await heading.getByRole('button').all())await expect(button).toHaveCSS('height',targetSize);
}
