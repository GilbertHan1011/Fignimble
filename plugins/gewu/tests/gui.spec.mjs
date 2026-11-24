import {cp, readFile} from 'node:fs/promises';
import {join} from 'node:path';

// Registered by `application-plugin.spec.mjs` with GEWU_APP_SPEC and GEWU_APP_PLUGIN.
export function register({test, expect, startFixture}) {
  test('opens a figure project, moves a panel and undoes it', async ({page}) => {
    test.setTimeout(300000);
    const fixture = await startFixture({settings: {}});
    try {
      await cp(new URL('../fixtures/project/', import.meta.url), join(fixture.root, 'figures/paper1'),
        {recursive: true});
      await page.goto(fixture.url);
      await expect(page.getByRole('textbox', {name: 'Message'})).toBeEnabled();

      const reveal = page.getByRole('button', {name: 'Show files'});
      if (await reveal.isVisible()) await reveal.click();
      await page.getByRole('tab', {name: 'PREVIEW'}).click();
      page.once('dialog', (dialog) => dialog.accept('figures/paper1'));
      await page.getByRole('button', {name: 'Open…', exact: true}).click();

      const editor = page.frameLocator('iframe[title="Figure editor"]');
      const source = () => readFile(join(fixture.root, 'figures/paper1/fig1.py'), 'utf8');
      await expect(editor.locator('#figures li')).toHaveCount(1, {timeout: 120000});
      await expect(editor.locator('#status')).toContainText('figures/paper1', {timeout: 120000});
      await expect(editor.locator('#figure img.sprite').first()).toHaveAttribute('src', /plugin-data/i);
      await expect(editor.locator('#layers li').first()).toBeVisible();

      // Select the panel in Layers, then drag its hit area on the canvas.
      await editor.locator('#layers li', {hasText: 'panel'}).first().click();
      await expect(editor.locator('#selection-title')).toContainText('panel');
      const before = await source();
      const hit = editor.locator('.hit[data-oid]').first();
      const box = await hit.boundingBox();
      await page.keyboard.down('Alt');
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2 + 72, box.y + box.height / 2 + 36, {steps: 10});
      await page.mouse.up();
      await page.keyboard.up('Alt');
      await expect.poll(source, {timeout: 120000}).not.toBe(before);
      await expect(editor.locator('#status')).toContainText('Move saved', {timeout: 120000});

      await editor.getByRole('button', {name: 'Undo'}).click();
      await expect(editor.locator('#status')).toContainText('Undid', {timeout: 120000});
      await expect.poll(source, {timeout: 120000}).toBe(before);
    } finally {
      await fixture.close();
    }
  });
}
