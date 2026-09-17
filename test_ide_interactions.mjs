export default async function run(page, ui) {
  const results = {
    timestamp: new Date().toISOString(),
    tests: []
  };

  // Test 1: Click on Chat button in sidebar
  try {
    const snapshot1 = await ui.snapshot();
    const chatButton = snapshot1.match(/@(e\d+) button "Chat"/)?.[1];
    if (chatButton) {
      await ui.click(chatButton);
      await page.waitForTimeout(500);
      const afterClick = await ui.snapshot();
      results.tests.push({
        test: "Click Chat button",
        passed: afterClick.includes("Chat"),
        snapshot: afterClick.substring(0, 200)
      });
    }
  } catch (e) {
    results.tests.push({ test: "Click Chat button", error: e.message });
  }

  // Test 2: Click on Files button in sidebar
  try {
    const snapshot2 = await ui.snapshot();
    const filesButton = snapshot2.match(/@(e\d+) button "Files"/)?.[1];
    if (filesButton) {
      await ui.click(filesButton);
      await page.waitForTimeout(500);
      const afterClick = await ui.snapshot();
      results.tests.push({
        test: "Click Files button",
        passed: afterClick.includes("Files"),
        snapshot: afterClick.substring(0, 200)
      });
    }
  } catch (e) {
    results.tests.push({ test: "Click Files button", error: e.message });
  }

  // Test 3: Click on Settings button
  try {
    const snapshot3 = await ui.snapshot();
    const settingsButton = snapshot3.match(/@(e\d+) button "Settings"/)?.[1];
    if (settingsButton) {
      await ui.click(settingsButton);
      await page.waitForTimeout(500);
      const afterClick = await ui.snapshot();
      results.tests.push({
        test: "Click Settings button",
        passed: afterClick.includes("Settings"),
        snapshot: afterClick.substring(0, 200)
      });
    }
  } catch (e) {
    results.tests.push({ test: "Click Settings button", error: e.message });
  }

  // Test 4: Type in terminal command
  try {
    const snapshot4 = await ui.snapshot();
    const terminalInput = snapshot4.match(/@(e\d+) textbox "Terminal command"/)?.[1];
    if (terminalInput) {
      await ui.fill(terminalInput, "ls -la");
      const afterFill = await ui.snapshot();
      results.tests.push({
        test: "Type in terminal",
        passed: afterFill.includes("ls -la"),
        snapshot: afterFill.substring(0, 200)
      });
    }
  } catch (e) {
    results.tests.push({ test: "Type in terminal", error: e.message });
  }

  // Test 5: Click on Work button
  try {
    const snapshot5 = await ui.snapshot();
    const workButton = snapshot5.match(/@(e\d+) button "◉ Work"/)?.[1];
    if (workButton) {
      await ui.click(workButton);
      await page.waitForTimeout(500);
      const afterClick = await ui.snapshot();
      results.tests.push({
        test: "Click Work button",
        passed: afterClick.includes("Work"),
        snapshot: afterClick.substring(0, 200)
      });
    }
  } catch (e) {
    results.tests.push({ test: "Click Work button", error: e.message });
  }

  // Take final screenshot
  await page.screenshot({ path: "C:\\Users\\jpowe\\Desktop\\Agent-Bridge\\ide_screenshot_after_tests.png" });

  return results;
}