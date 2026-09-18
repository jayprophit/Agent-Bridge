#pragma once

#include <string>
#include <unordered_map>

struct Item {
    std::string name;
    int quantity;

    Item(const std::string& name, int quantity) : name(name), quantity(quantity) {}

    bool operator==(const Item& other) const {
        return name == other.name && quantity == other.quantity;
    }

    bool operator!=(const Item& other) const {
        return !(*this == other);
    }
};

class Inventory {
private:
    std::unordered_map<std::string, Item> items;

public:
    Inventory() = default;

    void add_item(const std::string& name, int quantity);
    void remove_item(const std::string& name);
    void update_quantity(const std::string& name, int new_quantity);
    int query_quantity(const std::string& name) const;
    void list_items() const;

    bool reject_negative_quantities(int quantity) const;
};
